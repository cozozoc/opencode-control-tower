"""Immutable Phase 8 measurements and zero-false-abort verdicts."""

from __future__ import annotations

from dataclasses import dataclass

from octower.models import AgentState


@dataclass(frozen=True, slots=True)
class StateTransition:
    """One observed classifier transition for a persisted session."""

    session_id: str
    previous: AgentState
    current: AgentState
    occurred_at: float


@dataclass(frozen=True, slots=True)
class SoakMetrics:
    """Counters required by Phase 8 and handoff acceptance §26."""

    transitions: tuple[StateTransition, ...] = ()
    recovery_attempts: int = 0
    aborts: int = 0
    false_aborts: int = 0
    resume_count: int = 0
    done_count: int = 0
    stall_confirmations: int = 0
    parent_protection_events: int = 0
    journal_replays: int = 0
    backend_restarts: int = 0
    discovered_sessions: int = 0


@dataclass(frozen=True, slots=True)
class SoakReport:
    """Metrics plus assertion and protection violations determining process exit."""

    scenario: str
    metrics: SoakMetrics
    violations: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.violations and self.metrics.false_aborts == 0

    @property
    def aborts(self) -> int:
        return self.metrics.aborts

    @property
    def false_aborts(self) -> int:
        return self.metrics.false_aborts

    @property
    def resume_count(self) -> int:
        return self.metrics.resume_count

    @property
    def recovery_attempts(self) -> int:
        return self.metrics.recovery_attempts

    @property
    def done_count(self) -> int:
        return self.metrics.done_count

    @property
    def stall_confirmations(self) -> int:
        return self.metrics.stall_confirmations

    @property
    def parent_protection_events(self) -> int:
        return self.metrics.parent_protection_events

    @property
    def journal_replays(self) -> int:
        return self.metrics.journal_replays

    @property
    def backend_restarts(self) -> int:
        return self.metrics.backend_restarts

    @property
    def discovered_sessions(self) -> int:
        return self.metrics.discovered_sessions

    def render(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"{self.scenario}: {verdict} | sessions={self.discovered_sessions} "
            f"done={self.done_count} recoveries={self.recovery_attempts} "
            f"resumes={self.resume_count} aborts={self.aborts} "
            f"false_aborts={self.false_aborts} violations={len(self.violations)}"
        )
