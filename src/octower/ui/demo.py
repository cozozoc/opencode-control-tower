"""Offline demonstration data for terminal QA without an OpenCode process."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import anyio

from octower.models import AgentState
from octower.omo.doctor import (
    DoctorReport,
    OpenCodeApiCompatibility,
    ServerHealth,
    TmuxIntegration,
)
from octower.omo.policy import OmoPolicyConflict
from octower.recovery.journal import RecoveryPhase, RecoveryRecord
from octower.ui.data_source import AgentSnapshot, BoardEvent, BoardSnapshot


class DemoBoardDataSource:
    """Stable offline control-room sample; it never starts a server or process."""

    def __init__(self) -> None:
        self._agents = (
            _agent("ses-indexer", AgentState.RUNNING, "Indexing 482 symbols", "ses-root"),
            _agent("ses-tests", AgentState.WAITING, "Waiting on child result", "ses-root"),
            _agent("ses-recovery", AgentState.RECOVERING, "Resume accepted", "ses-tests"),
            _agent("ses-audit", AgentState.SUSPECT, "No semantic output for 11m", "ses-root"),
            _agent("ses-finished", AgentState.DONE, "Completed successfully", "ses-root"),
        )

    async def fetch_board(self) -> BoardSnapshot:
        return BoardSnapshot(self._agents)

    async def fetch_agent(self, session_id: str) -> AgentSnapshot | None:
        return next((agent for agent in self._agents if agent.session_id == session_id), None)

    async def fetch_history(self) -> tuple[RecoveryRecord, ...]:
        return (
            RecoveryRecord(
                "demo-recovery",
                "ses-recovery",
                "ses-root",
                "ses-tests",
                "confirmed silent stall",
                RecoveryPhase.RECOVERING,
                1,
                128.4,
                40.0,
                "demo",
            ),
        )

    async def fetch_doctor(self) -> DoctorReport:
        return DoctorReport(
            "1.18.15",
            OpenCodeApiCompatibility.SUPPORTED,
            True,
            "4.19.4",
            Path.home() / ".omo" / "omo.jsonc",
            180_000,
            OmoPolicyConflict.CONFLICT_CRITICAL,
            TmuxIntegration.UNAVAILABLE,
            "ses-root",
            Path.cwd(),
            ServerHealth.UNKNOWN,
            ">=3.11",
            ">=0.80",
        )

    async def events(self) -> AsyncIterator[BoardEvent]:
        await anyio.sleep_forever()
        yield BoardEvent.REFRESH


def _agent(
    session_id: str,
    state: AgentState,
    output: str,
    parent_id: str,
) -> AgentSnapshot:
    return AgentSnapshot(
        session_id,
        parent_id,
        session_id.removeprefix("ses-").replace("-", " ").title(),
        state,
        output,
        ("Agent discovered", output),
        (AgentState.DISCOVERED, state),
    )
