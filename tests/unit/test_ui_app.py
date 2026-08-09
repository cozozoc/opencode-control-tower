from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import anyio
from textual.widgets import DataTable

from octower.models import AgentState
from octower.omo.doctor import (
    DoctorReport,
    OpenCodeApiCompatibility,
    ServerHealth,
    TmuxIntegration,
)
from octower.omo.policy import OmoPolicyConflict
from octower.recovery.journal import RecoveryPhase, RecoveryRecord
from octower.ui.app import ControlTowerApp
from octower.ui.board import BoardScreen
from octower.ui.data_source import AgentSnapshot, BoardEvent, BoardSnapshot
from octower.ui.detail import DetailScreen


class FakeBoardDataSource:
    def __init__(self) -> None:
        self.agents = (
            _agent("ses-running", AgentState.RUNNING, "compiling index", parent="ses-root"),
            _agent("ses-waiting", AgentState.WAITING, "awaiting operator", parent="ses-root"),
            _agent("ses-recovering", AgentState.RECOVERING, "replaying journal", parent="ses-running"),
            _agent("ses-failed", AgentState.FAILED_RECOVERY, "attempt cap reached", parent="ses-root"),
            _agent("ses-done", AgentState.DONE, "completed", parent="ses-root"),
        )
        self.history = (
            RecoveryRecord(
                "rec-1",
                "ses-recovering",
                "ses-root",
                "ses-running",
                "confirmed silent stall",
                RecoveryPhase.RECOVERING,
                1,
                123.0,
                100.0,
                "native",
            ),
        )
        self.doctor = DoctorReport(
            "1.18.15",
            OpenCodeApiCompatibility.SUPPORTED,
            True,
            "4.19.4",
            Path("C:/Users/tester/.omo/omo.jsonc"),
            180_000,
            OmoPolicyConflict.CONFLICT_CRITICAL,
            TmuxIntegration.DISABLED,
            "ses-root",
            Path("C:/work/project"),
            ServerHealth.HEALTHY,
            ">=3.11",
            ">=0.80",
        )

    async def fetch_board(self) -> BoardSnapshot:
        return BoardSnapshot(self.agents)

    async def fetch_agent(self, session_id: str) -> AgentSnapshot | None:
        return next((agent for agent in self.agents if agent.session_id == session_id), None)

    async def fetch_history(self) -> tuple[RecoveryRecord, ...]:
        return self.history

    async def fetch_doctor(self) -> DoctorReport:
        return self.doctor

    async def events(self) -> AsyncIterator[BoardEvent]:
        await anyio.sleep_forever()
        yield BoardEvent.REFRESH


def test_board_renders_unfinished_agents_and_done_count() -> None:
    async def scenario() -> None:
        app = ControlTowerApp(FakeBoardDataSource(), poll_interval=3600)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            board = app.screen
            assert isinstance(board, BoardScreen)
            assert set(board.visible_session_ids) == {
                "ses-running",
                "ses-waiting",
                "ses-recovering",
                "ses-failed",
            }
            assert "ses-done" not in board.visible_session_ids
            assert "DONE 1" in str(board.query_one("#done-count").render())

    anyio.run(scenario)


def test_filter_searches_session_state_parent_and_text() -> None:
    async def scenario() -> None:
        app = ControlTowerApp(FakeBoardDataSource(), poll_interval=3600)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            board = app.screen
            assert isinstance(board, BoardScreen)
            filter_input = board.query_one("#filter-input")
            filter_input.value = "state:recovering parent:ses-running replaying"
            filter_input.focus()
            await app.refresh_now()
            await pilot.pause()
            assert board.visible_session_ids == ("ses-recovering",)
            assert filter_input.has_focus is True

    anyio.run(scenario)


def test_selection_survives_refresh_and_lane_change() -> None:
    async def scenario() -> None:
        source = FakeBoardDataSource()
        app = ControlTowerApp(source, poll_interval=3600)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            board = app.screen
            assert isinstance(board, BoardScreen)
            board.select_session("ses-running")
            running_table = board.query_one("#table-running", DataTable)
            source.agents = (
                _agent("ses-new", AgentState.DISCOVERED, "new child", parent="ses-root"),
                _agent("ses-running", AgentState.SLOW, "compiling index", parent="ses-root"),
                *source.agents[1:],
            )
            await app.refresh_now()
            await pilot.pause()
            assert app.selected_session_id == "ses-running"
            assert board.selected_session_id == "ses-running"
            assert board.query_one("#table-running", DataTable) is running_table

    anyio.run(scenario)


def test_detail_and_focus_show_selected_output() -> None:
    async def scenario() -> None:
        app = ControlTowerApp(FakeBoardDataSource(), poll_interval=3600)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            board = app.screen
            assert isinstance(board, BoardScreen)
            board.select_session("ses-recovering")
            assert "replaying journal" in str(board.query_one("#detail-output").render())
            await pilot.press("f")
            await pilot.pause()
            assert isinstance(app.screen, DetailScreen)
            assert "replaying journal" in str(app.screen.query_one("#focus-output").render())
            await pilot.press("f")
            assert isinstance(app.screen, BoardScreen)
            assert app.selected_session_id == "ses-recovering"

    anyio.run(scenario)


def test_history_and_doctor_render_core_models() -> None:
    async def scenario() -> None:
        app = ControlTowerApp(FakeBoardDataSource(), poll_interval=3600)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert "ses-recovering" in str(app.screen.query_one("#history-list").render())
            assert "RECOVERING" in str(app.screen.query_one("#history-list").render())
            await pilot.press("escape")
            await pilot.press("x")
            await pilot.pause()
            doctor_text = str(app.screen.query_one("#doctor-report").render())
            assert "CONFLICT_CRITICAL" in doctor_text
            assert "180000 ms" in doctor_text
            assert "1.18.15" in doctor_text

    anyio.run(scenario)


def _agent(
    session_id: str,
    state: AgentState,
    output: str,
    *,
    parent: str | None,
) -> AgentSnapshot:
    return AgentSnapshot(
        session_id=session_id,
        parent_id=parent,
        title=session_id.removeprefix("ses-").replace("-", " ").title(),
        state=state,
        output_preview=output,
        output_history=(f"started {session_id}", output),
        state_history=(AgentState.DISCOVERED, state),
    )
