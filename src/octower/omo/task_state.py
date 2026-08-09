"""Read-only OmO task-state mapping hooks for Phase 7 adapters (§3, Phase 6)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, assert_never


class OmoTaskState(str, Enum):
    """Adapter-neutral states obtainable from OmO evidence sources."""

    RUNNING = "running"
    TERMINAL = "terminal"
    UNKNOWN = "unknown"


class OmoTaskStateSource(Protocol):
    """Phase 7 hook for reading OmO state without wake or pane control."""

    def state_for_session(self, session_id: str) -> OmoTaskState: ...


@dataclass(frozen=True, slots=True)
class OmoTaskEvidence:
    """State-core flags that deliberately cannot request OmO native wake behavior."""

    running: bool
    terminal: bool
    wake_requested: bool = False


def map_task_state(state: OmoTaskState) -> OmoTaskEvidence:
    """Map all known OmO states to passive Guardian evidence."""
    match state:
        case OmoTaskState.RUNNING:
            return OmoTaskEvidence(True, False)
        case OmoTaskState.TERMINAL:
            return OmoTaskEvidence(False, True)
        case OmoTaskState.UNKNOWN:
            return OmoTaskEvidence(False, False)
        case unreachable:
            assert_never(unreachable)
