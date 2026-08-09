"""Passive OmO task-state hooks that never duplicate native wake behavior."""

from typing import assert_never

from .task_state import OmoTaskState, OmoTaskStateSource

OmOTaskState = OmoTaskState


def is_terminal_task_state(state: OmOTaskState) -> bool:
    """Map every OmO state to terminal evidence without side effects."""
    match state:
        case OmOTaskState.RUNNING | OmOTaskState.UNKNOWN:
            return False
        case OmOTaskState.TERMINAL:
            return True
        case unreachable:
            assert_never(unreachable)


__all__ = ["OmOTaskState", "OmoTaskStateSource", "is_terminal_task_state"]
