"""Data contracts for the Phase 2 state core (§6, §9-§12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Protocol


class Clock(Protocol):
    """Injectable monotonic clock used by state classification (§25)."""

    def now(self) -> float:
        """Return the current monotonic time in seconds."""


class AgentState(str, Enum):
    """Agent lifecycle and global safety states from §11."""

    DISCOVERED = "discovered"
    RUNNING = "running"
    SLOW = "slow"
    SUSPECT = "suspect"
    STALL_CONFIRMING = "stall_confirming"
    RECOVERING = "recovering"
    DONE = "done"
    WAITING = "waiting"
    FAILED_RECOVERY = "failed_recovery"
    BACKEND_DOWN = "backend_down"
    DEGRADED = "degraded"
    PAUSED = "paused"


@dataclass(slots=True)
class SessionNode:
    """A parentID-linked session node for recursive discovery (R1, §8)."""

    session_id: str
    parent_id: str | None = None
    title: str = ""
    child_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class CompletionEvidence:
    """Positive terminal evidence emitted by the completion classifier (§10)."""

    terminal: bool
    confidence: Literal["high", "medium", "low"]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticActivityRecord:
    """A meaningful semantic event used to advance activity time (§9)."""

    kind: str
    fingerprint: str
    occurred_at: float


@dataclass(frozen=True, slots=True)
class SessionEvidence:
    """Precomputed, adapter-neutral observations consumed by the classifier (§10-§12)."""

    session_id: str
    status: Literal["idle", "busy", "retry"] | None
    last_semantic_activity: float | None
    tool_states: tuple[str, ...] = ()
    todo_states: tuple[str, ...] = ()
    final_assistant_completed: bool = False
    final_assistant_intermediate: bool = False
    unresolved_error: bool = False
    adapter_task_running: bool = False
    adapter_terminal: bool = False
    human_waiting: bool = False
    active_descendant: bool = False
    backend_available: bool = True
    api_healthy: bool = True
    semantic_data_complete: bool = True
    data_consistent: bool = True
    recovery_in_progress: bool = False
    recovery_attempts: int = 0
    recovery_started_at: float | None = None
    paused: bool = False


@dataclass(frozen=True, slots=True)
class ThresholdConfig:
    """Configurable 5/10/15-minute policy plus §12 confirmation settings."""

    slow_seconds: float = 300
    suspect_seconds: float = 600
    stall_seconds: float = 900
    stall_confirm_seconds: float = 60
    stall_confirm_samples: int = 4
    max_recovery_attempts: int = 2

    def __post_init__(self) -> None:
        if not 0 < self.slow_seconds < self.suspect_seconds < self.stall_seconds:
            raise ValueError("thresholds must satisfy 0 < slow < suspect < stall")
        if self.stall_confirm_seconds <= 0 or self.stall_confirm_samples <= 0:
            raise ValueError("confirmation window and samples must be positive")
        if self.max_recovery_attempts <= 0:
            raise ValueError("max_recovery_attempts must be positive")


@dataclass(frozen=True, slots=True)
class ConfirmationProgress:
    """Sample/window bookkeeping for STALL_CONFIRMING (§12)."""

    started_at: float
    samples: int


@dataclass(frozen=True, slots=True)
class Classification:
    """Pure classifier output; Phase 2 intentionally performs no actions (§27)."""

    state: AgentState
    completion: CompletionEvidence
    silence_seconds: float | None
    reasons: tuple[str, ...]
    confirmation: ConfirmationProgress | None = None
