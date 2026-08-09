"""Full-stack deterministic Guardian lifecycle driver for Phase 8."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from octower.discovery.reconciliation import SessionReconciler
from octower.models import AgentState, Classification, ConfirmationProgress
from octower.recovery.engine import RecoveryEngine
from octower.recovery.journal import RecoveryJournal
from octower.recovery.parent_wake import ParentWakeCoordinator
from octower.soak.metrics import SoakMetrics, SoakReport, StateTransition
from octower.soak.provider import ActionKind, DeterministicProvider, ProviderAction
from octower.state.classifier import AgentStateClassifier


@dataclass(frozen=True, slots=True)
class SessionOutcome:
    """Final observed state for one dynamically discovered session."""

    session_id: str
    state: AgentState


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Scenario verdict with final states and auditable provider operations."""

    report: SoakReport
    outcomes: tuple[SessionOutcome, ...]
    actions: tuple[ProviderAction, ...]
    resumed_session_ids: tuple[str, ...] = ()
    automatic_recovery_armed: bool = True

    @property
    def action_session_ids(self) -> tuple[str, ...]:
        return tuple(action.session_id for action in self.actions)

    def state_for(self, session_id: str) -> AgentState:
        return next(outcome.state for outcome in self.outcomes if outcome.session_id == session_id)


class SoakHarness:
    """Compose reconciliation, state, recovery, journal, and parent wake layers."""

    def __init__(
        self,
        root_session_id: str,
        provider: DeterministicProvider,
        journal_path: Path,
        *,
        automatic_recovery_armed: bool = True,
    ) -> None:
        self.provider = provider
        self.clock = provider.clock
        self.journal = RecoveryJournal(journal_path)
        self.reconciler = SessionReconciler(root_session_id, provider)
        self.classifier = AgentStateClassifier(self.clock)
        self.recovery = RecoveryEngine(provider, self.journal, self.clock, adapter="soak-mock")
        self.parent_wake = ParentWakeCoordinator(
            provider, self.journal, self.clock, adapter="soak-mock"
        )
        self.automatic_recovery_armed = automatic_recovery_armed
        self._states: dict[str, AgentState] = {}
        self._confirmations: dict[str, ConfirmationProgress] = {}
        self._transitions: list[StateTransition] = []
        self._recovery_attempts = 0
        self._stall_confirmations = 0
        self._parent_protections = 0
        self._journal_replays = 0

    def advance_and_sample(self, seconds: float) -> None:
        self.clock.advance(seconds)
        self.sample()

    def sample(self) -> None:
        self.reconciler.reconcile()
        nodes = self.reconciler.tree.nodes()
        for node in nodes:
            evidence = self.provider.get_evidence(node.session_id)
            previous = self._states.get(node.session_id, AgentState.DISCOVERED)
            classified = self.classifier.classify(evidence, previous)
            classified = self._confirm(node.session_id, evidence.status, classified)
            self._record(node.session_id, previous, classified.state)
            state = self._recover(node.session_id, node.parent_id, classified)
            if evidence.active_descendant and state is AgentState.WAITING:
                self._parent_protections += 1
            self._record(node.session_id, classified.state, state)
        self._wake_completed_parents()

    def replay(self) -> None:
        results = self.recovery.replay()
        self._journal_replays += len(results)
        for result in results:
            self._record(
                result.session_id,
                self._states.get(result.session_id, AgentState.DISCOVERED),
                result.state,
            )

    def result(
        self,
        scenario: str,
        *,
        violations: tuple[str, ...] = (),
        backend_restarts: int = 0,
        resumed_session_ids: tuple[str, ...] | None = None,
    ) -> ScenarioResult:
        abort_actions = tuple(
            action for action in self.provider.actions if action.kind is ActionKind.ABORT
        )
        prompt_actions = tuple(
            action for action in self.provider.actions if action.kind is ActionKind.PROMPT_ASYNC
        )
        protected_aborts = tuple(action for action in abort_actions if action.was_protected)
        journal_attempts = sum(
            record.phase.value == "INTENT" and record.attempt > 0
            for record in self.journal.read()
        )
        protection_violations = tuple(
            f"protected session aborted: {action.session_id}" for action in protected_aborts
        )
        metrics = SoakMetrics(
            transitions=tuple(self._transitions),
            recovery_attempts=journal_attempts,
            aborts=len(abort_actions),
            false_aborts=len(protected_aborts),
            resume_count=len(prompt_actions) + (
                len(resumed_session_ids) if resumed_session_ids is not None else 0
            ),
            done_count=sum(state is AgentState.DONE for state in self._states.values()),
            stall_confirmations=self._stall_confirmations,
            parent_protection_events=self._parent_protections,
            journal_replays=self._journal_replays,
            backend_restarts=backend_restarts,
            discovered_sessions=len(self._states),
        )
        resumes = resumed_session_ids or tuple(action.session_id for action in prompt_actions)
        return ScenarioResult(
            SoakReport(scenario, metrics, violations + protection_violations),
            tuple(SessionOutcome(session_id, state) for session_id, state in self._states.items()),
            tuple(self.provider.actions),
            resumes,
            self.automatic_recovery_armed,
        )

    def force_state(self, session_id: str, state: AgentState) -> None:
        self._record(session_id, self._states.get(session_id, AgentState.DISCOVERED), state)

    def _confirm(
        self, session_id: str, status: str | None, classified: Classification
    ) -> Classification:
        if classified.state is not AgentState.STALL_CONFIRMING:
            self._confirmations.pop(session_id, None)
            return classified
        evidence = self.provider.get_evidence(session_id)
        confirmed = self.classifier.confirm_candidate(
            evidence, self._confirmations.get(session_id)
        )
        if confirmed.confirmation is not None:
            self._confirmations[session_id] = confirmed.confirmation
        if confirmed.state is AgentState.RECOVERING and status == "busy":
            self._stall_confirmations += 1
        return confirmed

    def _recover(
        self, session_id: str, parent_id: str | None, classified: Classification
    ) -> AgentState:
        if not self.automatic_recovery_armed:
            return classified.state
        evidence = self.provider.get_evidence(session_id)
        if classified.state is AgentState.RUNNING and self.journal.active(session_id):
            return self.recovery.poll(session_id).state
        if classified.state is AgentState.SUSPECT and evidence.status == "idle":
            self._recovery_attempts += 1
            return self.recovery.soft_resume(
                session_id, root_session_id=self.reconciler.root_id, parent_id=parent_id
            ).state
        if classified.state is AgentState.RECOVERING and evidence.status == "busy":
            self._recovery_attempts += 1
            return self.recovery.hard_resume(
                session_id, root_session_id=self.reconciler.root_id, parent_id=parent_id
            ).state
        if classified.state is AgentState.RECOVERING and self.journal.active(session_id):
            return self.recovery.poll(session_id).state
        return classified.state

    def _record(self, session_id: str, previous: AgentState, current: AgentState) -> None:
        if previous is not current:
            self._transitions.append(
                StateTransition(session_id, previous, current, self.clock.now())
            )
        self._states[session_id] = current

    def _wake_completed_parents(self) -> None:
        for node in self.reconciler.tree.nodes():
            if self._states.get(node.session_id) is not AgentState.DONE or node.parent_id is None:
                continue
            parent = self.reconciler.tree.get(node.parent_id)
            if parent is None:
                continue
            siblings = tuple(
                sibling
                for sibling_id in parent.child_ids
                if (sibling := self.reconciler.tree.get(sibling_id)) is not None
            )
            result = self.parent_wake.on_child_done(
                node.parent_id,
                tuple(self.provider.get_evidence(sibling.session_id) for sibling in siblings),
                root_session_id=self.reconciler.root_id,
            )
            if result.woken:
                self._record(
                    node.parent_id,
                    self._states.get(node.parent_id, AgentState.DISCOVERED),
                    AgentState.RECOVERING,
                )
