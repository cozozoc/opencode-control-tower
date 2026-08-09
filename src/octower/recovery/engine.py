"""Adapter-neutral soft, hard, and replayable recovery transactions (§13)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from octower.models import AgentState, Clock, SessionEvidence, ThresholdConfig
from octower.recovery.journal import RecoveryJournal, RecoveryPhase, RecoveryRecord
from octower.recovery.prompts import DEFAULT_RECOVERY_PROMPT
from octower.state.completion import classify_completion
from octower.state.invariants import inv_002_same_session, stall_guards

RECOVERY_ACTIVITY_TIMEOUT = 300.0
RECOVERY_COOLDOWN = 300.0


class RecoveryActions(Protocol):
    """Minimal synchronous runtime operations required by the Phase 3 core (§7.1)."""

    def abort_session(self, session_id: str) -> bool:
        """Request termination of the current turn for one existing session."""

    def prompt_async(self, session_id: str, text: str) -> bool:
        """Send a continuation message to one existing session."""

    def validate_session(self, session_id: str) -> bool:
        """Report whether the preserved session still exists."""

    def get_evidence(self, session_id: str) -> SessionEvidence:
        """Return fresh adapter-neutral evidence for one session."""


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Observable outcome of one safe recovery-engine pass (§13.4-§13.5)."""

    state: AgentState
    session_id: str
    recovery_id: str | None
    reason: str
    action_performed: bool = False


class RecoveryEngine:
    """Continue durable same-session recovery records without duplicate actions."""

    def __init__(
        self,
        actions: RecoveryActions,
        journal: RecoveryJournal,
        clock: Clock,
        config: ThresholdConfig | None = None,
        recovery_prompt: str = DEFAULT_RECOVERY_PROMPT,
        adapter: str = "native-opencode",
    ) -> None:
        self._actions = actions
        self._journal = journal
        self._clock = clock
        self._config = config or ThresholdConfig()
        self._recovery_prompt = recovery_prompt
        self._adapter = adapter

    def soft_resume(
        self,
        session_id: str,
        *,
        root_session_id: str | None = None,
        parent_id: str | None = None,
    ) -> RecoveryResult:
        """Continue an eligible idle unfinished session without aborting it (Case D)."""
        evidence = self._actions.get_evidence(session_id)
        active = self._active(session_id)
        if active is not None:
            return self._continue(active, evidence)
        if evidence.status != "idle" or not self._safe(evidence):
            return self._blocked(session_id, "soft resume requires eligible idle unfinished evidence")
        record = self._start(session_id, root_session_id, parent_id, "idle_unfinished", evidence)
        if record is None:
            return self._blocked(session_id, "recovery attempts exhausted or cooldown active")
        return self._validate_then_resume(record, evidence)

    def hard_resume(
        self,
        session_id: str,
        *,
        root_session_id: str | None = None,
        parent_id: str | None = None,
    ) -> RecoveryResult:
        """Abort a confirmed silent busy stall then resume its same session (Case E)."""
        evidence = self._actions.get_evidence(session_id)
        active = self._active(session_id)
        if active is not None:
            return self._continue(active, evidence)
        if evidence.status != "busy" or not self._safe(evidence):
            return self._blocked(session_id, "hard resume requires eligible confirmed busy stall evidence")
        record = self._start(session_id, root_session_id, parent_id, "confirmed_silent_stall_15m", evidence)
        if record is None:
            return self._blocked(session_id, "recovery attempts exhausted or cooldown active")
        requested = self._journal.advance(record, RecoveryPhase.ABORT_REQUESTED, self._clock.now())
        if not self._actions.abort_session(session_id):
            self._journal.advance(requested, RecoveryPhase.FAILED, self._clock.now())
            return self._result(AgentState.FAILED_RECOVERY, requested, "abort request was rejected", True)
        return self._continue(requested, self._actions.get_evidence(session_id), True)

    def poll(self, session_id: str) -> RecoveryResult:
        """Reconcile an in-flight transaction and confirm post-resume activity (§13.4)."""
        evidence = self._actions.get_evidence(session_id)
        active = self._active(session_id)
        if active is None:
            return self._blocked(session_id, "no recovery transaction is in progress")
        return self._continue(active, evidence)

    def replay(self, session_id: str | None = None) -> tuple[RecoveryResult, ...]:
        """Safely continue durable in-flight records after a Control Tower restart (§13.2)."""
        return tuple(
            self._continue(record, self._actions.get_evidence(record.session_id))
            for record in self._journal.active(session_id)
        )

    def _continue(
        self, record: RecoveryRecord, evidence: SessionEvidence, action_performed: bool = False
    ) -> RecoveryResult:
        if record.phase is RecoveryPhase.INTENT and record.reason == "confirmed_silent_stall_15m":
            requested = self._journal.advance(record, RecoveryPhase.ABORT_REQUESTED, self._clock.now())
            if not self._actions.abort_session(record.session_id):
                self._journal.advance(requested, RecoveryPhase.FAILED, self._clock.now())
                return self._result(AgentState.FAILED_RECOVERY, requested, "abort request was rejected", True)
            return self._continue(requested, self._actions.get_evidence(record.session_id), True)
        if record.phase is RecoveryPhase.ABORT_REQUESTED:
            if evidence.status == "busy":
                return self._result(AgentState.RECOVERING, record, "awaiting non-busy abort confirmation", action_performed)
            confirmed = self._journal.advance(record, RecoveryPhase.ABORT_CONFIRMED, self._clock.now())
            return self._validate_then_resume(confirmed, evidence, action_performed)
        if record.phase in {RecoveryPhase.INTENT, RecoveryPhase.ABORT_CONFIRMED}:
            return self._validate_then_resume(record, evidence, action_performed)
        if record.phase is RecoveryPhase.SESSION_REVALIDATED:
            return self._request_resume(record, action_performed)
        if record.phase in {RecoveryPhase.RESUME_REQUESTED, RecoveryPhase.RECOVERING}:
            return self._monitor(record, evidence, action_performed)
        return self._result(AgentState.RECOVERING, record, "recovery journal is awaiting reconciliation", action_performed)

    def _validate_then_resume(
        self, record: RecoveryRecord, evidence: SessionEvidence, action_performed: bool = False
    ) -> RecoveryResult:
        if not self._actions.validate_session(record.session_id):
            self._journal.advance(record, RecoveryPhase.FAILED, self._clock.now())
            return self._result(AgentState.FAILED_RECOVERY, record, "same session no longer exists", action_performed)
        validated = self._journal.advance(record, RecoveryPhase.SESSION_REVALIDATED, self._clock.now())
        return self._request_resume(validated, action_performed)

    def _request_resume(self, record: RecoveryRecord, action_performed: bool = False) -> RecoveryResult:
        same_session = inv_002_same_session(record.session_id, record.session_id)
        if not same_session.passed:
            self._journal.advance(record, RecoveryPhase.FAILED, self._clock.now())
            return self._result(AgentState.FAILED_RECOVERY, record, same_session.reason, action_performed)
        requested = self._journal.advance(record, RecoveryPhase.RESUME_REQUESTED, self._clock.now())
        accepted = self._actions.prompt_async(record.session_id, self._recovery_prompt)
        if accepted:
            self._journal.advance(requested, RecoveryPhase.RECOVERING, self._clock.now())
        return self._result(AgentState.RECOVERING, requested, "same-session continuation requested", action_performed or accepted)

    def _monitor(
        self, record: RecoveryRecord, evidence: SessionEvidence, action_performed: bool
    ) -> RecoveryResult:
        requested = self._resume_request(record)
        if evidence.last_semantic_activity is not None and evidence.last_semantic_activity > requested.created_at:
            confirmed = self._journal.advance(record, RecoveryPhase.ACTIVITY_CONFIRMED, self._clock.now())
            self._journal.advance(confirmed, RecoveryPhase.RECOVERED, self._clock.now())
            return self._result(AgentState.RUNNING, record, "new semantic activity confirmed", action_performed)
        if self._clock.now() - requested.created_at < RECOVERY_ACTIVITY_TIMEOUT:
            return self._result(AgentState.RECOVERING, record, "awaiting semantic activity after resume", action_performed)
        self._journal.advance(record, RecoveryPhase.FAILED, self._clock.now())
        if not self._safe(evidence):
            return self._result(AgentState.FAILED_RECOVERY, record, "recovery activity timed out and retry is unsafe", action_performed)
        if evidence.status == "busy":
            return self.hard_resume(record.session_id, root_session_id=record.root_session_id, parent_id=record.parent_id)
        if evidence.status == "idle":
            return self.soft_resume(record.session_id, root_session_id=record.root_session_id, parent_id=record.parent_id)
        return self._result(AgentState.FAILED_RECOVERY, record, "recovery activity timed out", action_performed)

    def _start(
        self,
        session_id: str,
        root_session_id: str | None,
        parent_id: str | None,
        reason: str,
        evidence: SessionEvidence,
    ) -> RecoveryRecord | None:
        attempts = max(evidence.recovery_attempts, self._highest_attempt(session_id))
        if attempts >= self._config.max_recovery_attempts or not self._cooled_down(session_id):
            return None
        return self._journal.start(
            session_id=session_id,
            root_session_id=root_session_id or session_id,
            parent_id=parent_id,
            reason=reason,
            attempt=attempts + 1,
            created_at=self._clock.now(),
            last_activity_before=evidence.last_semantic_activity,
            adapter=self._adapter,
        )

    def _safe(self, evidence: SessionEvidence) -> bool:
        completion = classify_completion(evidence)
        guards = stall_guards(evidence, completion, self._config.max_recovery_attempts)
        return all(guard.passed for index, guard in enumerate(guards) if index != 6)

    def _active(self, session_id: str) -> RecoveryRecord | None:
        records = self._journal.active(session_id)
        return max(records, key=lambda record: (record.attempt, record.created_at), default=None)

    def _highest_attempt(self, session_id: str) -> int:
        return max((record.attempt for record in self._journal.records_for(session_id)), default=0)

    def _cooled_down(self, session_id: str) -> bool:
        starts = [record for record in self._journal.records_for(session_id) if record.phase is RecoveryPhase.INTENT]
        return not starts or self._clock.now() - starts[-1].created_at >= RECOVERY_COOLDOWN

    def _resume_request(self, record: RecoveryRecord) -> RecoveryRecord:
        return next(
            item for item in reversed(self._journal.records_for(record.session_id))
            if item.recovery_id == record.recovery_id and item.phase is RecoveryPhase.RESUME_REQUESTED
        )

    @staticmethod
    def _result(state: AgentState, record: RecoveryRecord, reason: str, action_performed: bool) -> RecoveryResult:
        return RecoveryResult(state, record.session_id, record.recovery_id, reason, action_performed)

    @staticmethod
    def _blocked(session_id: str, reason: str) -> RecoveryResult:
        return RecoveryResult(AgentState.FAILED_RECOVERY, session_id, None, reason)
