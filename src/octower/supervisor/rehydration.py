"""Conservative R11 root, journal, and session-resume contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, assert_never

from octower.models import AgentState


class RootRestoreState(str, Enum):
    """Fail-safe root restoration outcomes after backend restart."""

    READY = "ready"
    MISSING = "missing"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class RehydratedSession:
    """Prior and fresh classification used to gate post-restart continuation."""

    session_id: str
    prior_state: AgentState
    current_state: AgentState
    unfinished: bool


class RehydrationActions(Protocol):
    """R11 persistence, root, journal, classifier, and continuation boundary."""

    async def reenumerate_sessions(self) -> tuple[str, ...]: ...

    async def restore_root(
        self, root_id: str, sessions: tuple[str, ...]
    ) -> RootRestoreState: ...

    async def reload_journal(self) -> tuple[str, ...]: ...

    async def reclassify(
        self, sessions: tuple[str, ...], recovering_sessions: tuple[str, ...]
    ) -> tuple[RehydratedSession, ...]: ...

    async def resume(self, session_id: str) -> None: ...


def eligible_for_resume(session: RehydratedSession) -> bool:
    """Allow only previously active/recovering sessions that remain unfinished."""
    if not session.unfinished:
        return False
    match session.prior_state:
        case (
            AgentState.RUNNING
            | AgentState.SLOW
            | AgentState.SUSPECT
            | AgentState.STALL_CONFIRMING
            | AgentState.RECOVERING
        ):
            pass
        case (
            AgentState.DISCOVERED
            | AgentState.DONE
            | AgentState.WAITING
            | AgentState.FAILED_RECOVERY
            | AgentState.BACKEND_DOWN
            | AgentState.DEGRADED
            | AgentState.PAUSED
        ):
            return False
        case unreachable:
            assert_never(unreachable)
    match session.current_state:
        case AgentState.DONE | AgentState.FAILED_RECOVERY:
            return False
        case (
            AgentState.DISCOVERED
            | AgentState.RUNNING
            | AgentState.SLOW
            | AgentState.SUSPECT
            | AgentState.STALL_CONFIRMING
            | AgentState.RECOVERING
            | AgentState.WAITING
            | AgentState.BACKEND_DOWN
            | AgentState.DEGRADED
            | AgentState.PAUSED
        ):
            return True
        case unreachable:
            assert_never(unreachable)
