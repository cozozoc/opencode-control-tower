"""Idempotent parent-orchestration continuation after terminal child work (§14)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from octower.models import Clock, SessionEvidence, ThresholdConfig
from octower.recovery.journal import RecoveryJournal, RecoveryPhase
from octower.recovery.prompts import DEFAULT_PARENT_WAKE_PROMPT
from octower.state.completion import classify_completion
from octower.state.invariants import inv_002_same_session, stall_guards


class ParentWakeActions(Protocol):
    """Operations required to inspect and continue a same-session parent (§14)."""

    def get_evidence(self, session_id: str) -> SessionEvidence:
        """Return fresh adapter-neutral parent evidence."""

    def prompt_async(self, session_id: str, text: str) -> bool:
        """Send an asynchronous continuation to the existing parent session."""


@dataclass(frozen=True, slots=True)
class ParentWakeResult:
    """Outcome of one R10 parent wake eligibility evaluation."""

    woken: bool
    parent_session_id: str
    reason: str


class ParentWakeCoordinator:
    """Wake an idle unfinished parent exactly once after all relevant children finish."""

    def __init__(
        self,
        actions: ParentWakeActions,
        journal: RecoveryJournal,
        clock: Clock,
        config: ThresholdConfig | None = None,
        parent_wake_prompt: str = DEFAULT_PARENT_WAKE_PROMPT,
        adapter: str = "native-opencode",
    ) -> None:
        self._actions = actions
        self._journal = journal
        self._clock = clock
        self._config = config or ThresholdConfig()
        self._prompt = parent_wake_prompt
        self._adapter = adapter

    def on_child_done(
        self,
        parent_session_id: str,
        children: Sequence[SessionEvidence],
        *,
        root_session_id: str | None = None,
        wake_already_dispatched: bool = False,
    ) -> ParentWakeResult:
        """Evaluate all R10 conditions when a child becomes terminal."""
        if not children or not all(classify_completion(child).terminal for child in children):
            return ParentWakeResult(False, parent_session_id, "relevant children are not all terminal")
        if wake_already_dispatched:
            return ParentWakeResult(False, parent_session_id, "native adapter already dispatched parent wake")
        if self._journal.has_parent_wake(parent_session_id):
            return ParentWakeResult(False, parent_session_id, "parent wake already journaled")
        parent = self._actions.get_evidence(parent_session_id)
        completion = classify_completion(parent)
        if completion.terminal:
            return ParentWakeResult(False, parent_session_id, "parent is already terminal")
        if parent.status != "idle":
            return ParentWakeResult(False, parent_session_id, "parent is not idle")
        guards = stall_guards(parent, completion, self._config.max_recovery_attempts)
        failed = next((guard for guard in guards if not guard.passed), None)
        if failed is not None:
            return ParentWakeResult(False, parent_session_id, failed.reason)
        same_session = inv_002_same_session(parent_session_id, parent_session_id)
        if not same_session.passed:
            return ParentWakeResult(False, parent_session_id, same_session.reason)
        intent = self._journal.start(
            session_id=parent_session_id,
            root_session_id=root_session_id or parent_session_id,
            parent_id=None,
            reason="all_relevant_children_terminal",
            attempt=0,
            created_at=self._clock.now(),
            last_activity_before=parent.last_semantic_activity,
            adapter=self._adapter,
        )
        self._journal.advance(intent, RecoveryPhase.PARENT_WAKE_REQUESTED, self._clock.now())
        accepted = self._actions.prompt_async(parent_session_id, self._prompt)
        return ParentWakeResult(accepted, parent_session_id, "parent continuation requested" if accepted else "parent wake was rejected")

    def wake_parent_if_ready(
        self,
        parent_session_id: str,
        children: Sequence[SessionEvidence],
        *,
        root_session_id: str | None = None,
        wake_already_dispatched: bool = False,
    ) -> ParentWakeResult:
        """Alias exposing the default parent wake policy as an explicit operation."""
        return self.on_child_done(
            parent_session_id,
            children,
            root_session_id=root_session_id,
            wake_already_dispatched=wake_already_dispatched,
        )
