"""Scripted provider with NativeOpenCodeAdapter-shaped evidence (§25)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from octower.api.opencode import Session
from octower.models import SessionEvidence


SessionStatus = Literal["idle", "busy", "retry"]


class ActionKind(str, Enum):
    """Observable provider operations used to audit INV-002 and INV-009."""

    ABORT = "abort"
    PROMPT_ASYNC = "prompt_async"


class HumanWaitKind(str, Enum):
    """OpenCode human-interaction waits protected by INV-005."""

    PERMISSION = "permission"
    QUESTION = "question"


@dataclass(frozen=True, slots=True)
class ScriptedEvent:
    """One evidence snapshot activated at a deterministic session-relative time."""

    after_seconds: float
    status: SessionStatus = "busy"
    provider_retry: bool = False
    tool_running: bool = False
    human_waiting: bool = False
    human_wait_kind: HumanWaitKind | None = None
    final_assistant_completed: bool = False
    unresolved_error: bool = False
    backend_available: bool = True
    api_healthy: bool = True
    semantic_data_complete: bool = True
    data_consistent: bool = True
    recovery_attempts: int = 0
    adapter_terminal: bool = False


@dataclass(frozen=True, slots=True)
class SessionScript:
    """Fully controlled event stream for one persisted OpenCode session."""

    session_id: str
    parent_id: str | None
    events: tuple[ScriptedEvent, ...]
    discover_after_seconds: float = 0
    continuation_delay_seconds: float = 1

    def __post_init__(self) -> None:
        if not self.events:
            raise ValueError("a session script requires at least one event")
        if tuple(sorted(self.events, key=lambda event: event.after_seconds)) != self.events:
            raise ValueError("session events must be ordered by activation time")


@dataclass(frozen=True, slots=True)
class ProviderAction:
    """Auditable same-session action plus protections present at decision time."""

    kind: ActionKind
    session_id: str
    occurred_at: float
    retry_protected: bool
    tool_protected: bool
    human_protected: bool
    parent_protected: bool

    @property
    def was_protected(self) -> bool:
        return (
            self.retry_protected
            or self.tool_protected
            or self.human_protected
            or self.parent_protected
        )


class ManualClock:
    """Accelerated monotonic clock; advancing it never sleeps."""

    def __init__(self, start: float = 0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("clock cannot move backwards")
        self._now += seconds


class DeterministicProvider:
    """In-memory provider implementing recovery and reconciliation boundaries."""

    def __init__(self, clock: ManualClock, scripts: tuple[SessionScript, ...]) -> None:
        self.clock = clock
        self._started_at = clock.now()
        self._scripts = {script.session_id: script for script in scripts}
        self._aborted: set[str] = set()
        self._prompted_at: dict[str, float] = {}
        self.actions: list[ProviderAction] = []

    def list_sessions(self) -> list[Session]:
        return [
            Session(script.session_id, title=script.session_id, parent_id=script.parent_id)
            for script in self._scripts.values()
            if self._discovered(script)
        ]

    def get_children(self, session_id: str) -> list[Session]:
        return [session for session in self.list_sessions() if session.parent_id == session_id]

    def get_evidence(self, session_id: str) -> SessionEvidence:
        script = self._scripts[session_id]
        event = self._event(script)
        prompted_at = self._prompted_at.get(session_id)
        continuation_ready = prompted_at is not None and (
            self.clock.now() - prompted_at >= script.continuation_delay_seconds
        )
        status = event.status
        last_activity = self._started_at + event.after_seconds
        recovery_in_progress = False
        if session_id in self._aborted:
            status = "idle"
        if prompted_at is not None and not event.final_assistant_completed:
            status = "busy"
            recovery_in_progress = not continuation_ready
            if continuation_ready:
                last_activity = prompted_at + script.continuation_delay_seconds
        children = self.get_children(session_id)
        active_descendant = any(self._active(self.get_evidence(child.id)) for child in children)
        return SessionEvidence(
            session_id=session_id,
            status="retry" if event.provider_retry else status,
            last_semantic_activity=last_activity,
            tool_states=("running",) if event.tool_running else (),
            final_assistant_completed=event.final_assistant_completed,
            final_assistant_intermediate=event.tool_running,
            unresolved_error=event.unresolved_error,
            adapter_task_running=event.provider_retry,
            adapter_terminal=event.adapter_terminal,
            human_waiting=event.human_waiting or event.human_wait_kind is not None,
            active_descendant=active_descendant,
            backend_available=event.backend_available,
            api_healthy=event.api_healthy,
            semantic_data_complete=event.semantic_data_complete,
            data_consistent=event.data_consistent,
            recovery_in_progress=recovery_in_progress,
            recovery_attempts=event.recovery_attempts,
            recovery_started_at=prompted_at,
        )

    def abort_session(self, session_id: str) -> bool:
        evidence = self.get_evidence(session_id)
        self.actions.append(self._action(ActionKind.ABORT, evidence))
        self._aborted.add(session_id)
        self._prompted_at.pop(session_id, None)
        return True

    def prompt_async(self, session_id: str, text: str) -> bool:
        del text
        evidence = self.get_evidence(session_id)
        self.actions.append(self._action(ActionKind.PROMPT_ASYNC, evidence))
        self._prompted_at[session_id] = self.clock.now()
        self._aborted.discard(session_id)
        return True

    def validate_session(self, session_id: str) -> bool:
        return session_id in self._scripts and self._discovered(self._scripts[session_id])

    def _event(self, script: SessionScript) -> ScriptedEvent:
        elapsed = self.clock.now() - self._started_at
        return next(
            event
            for event in reversed(script.events)
            if event.after_seconds <= elapsed
        )

    def _discovered(self, script: SessionScript) -> bool:
        return self.clock.now() - self._started_at >= script.discover_after_seconds

    @staticmethod
    def _active(evidence: SessionEvidence) -> bool:
        return (
            evidence.status in {"busy", "retry"}
            or any(state in {"pending", "running"} for state in evidence.tool_states)
            or evidence.active_descendant
        )

    def _action(self, kind: ActionKind, evidence: SessionEvidence) -> ProviderAction:
        return ProviderAction(
            kind,
            evidence.session_id,
            self.clock.now(),
            evidence.status == "retry",
            any(state in {"pending", "running"} for state in evidence.tool_states),
            evidence.human_waiting,
            evidence.active_descendant,
        )
