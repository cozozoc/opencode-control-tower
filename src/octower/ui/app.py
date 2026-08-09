"""Professional asynchronous Textual control room from handoff §26-§27."""

from __future__ import annotations

from textual import work
from textual.app import App
from textual.binding import Binding

from octower.ui.board import BoardScreen
from octower.ui.data_source import BoardDataSource
from octower.ui.detail import DetailScreen
from octower.ui.doctor_screen import DoctorScreen
from octower.ui.history import HistoryScreen
from octower.ui.theme import CONTROL_TOWER_THEME


class ControlTowerApp(App[None]):
    """Responsive polling/SSE shell with an injected read-only data source."""

    TITLE = "OpenCode Control Tower"
    SUB_TITLE = "Background Agent Operations"
    CSS_PATH = "control_tower.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f", "focus_agent", "Focus"),
        Binding("/", "search", "Filter"),
        Binding("h", "show_history", "History"),
        Binding("x", "show_doctor", "Doctor"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, data_source: BoardDataSource, poll_interval: float = 2.0) -> None:
        super().__init__()
        self.data_source = data_source
        self.poll_interval = poll_interval
        self.selected_session_id: str | None = None
        self.board_screen = BoardScreen()

    async def on_mount(self) -> None:
        self.register_theme(CONTROL_TOWER_THEME)
        self.theme = CONTROL_TOWER_THEME.name
        await self.push_screen(self.board_screen)
        self.refresh_board()
        self.consume_events()
        self.set_interval(self.poll_interval, self.refresh_board)

    async def refresh_now(self) -> None:
        snapshot = await self.data_source.fetch_board()
        self.board_screen.apply_snapshot(snapshot)

    @work(group="board-refresh", exclusive=True)
    async def refresh_board(self) -> None:
        await self.refresh_now()

    @work(group="sse-events", exclusive=True)
    async def consume_events(self) -> None:
        async for _event in self.data_source.events():
            self.refresh_board()

    def action_refresh(self) -> None:
        self.refresh_board()

    def action_search(self) -> None:
        self.board_screen.query_one("#filter-input").focus()

    def action_focus_agent(self) -> None:
        session_id = self.selected_session_id
        if session_id is not None:
            self.open_detail(session_id)

    @work(group="detail", exclusive=True)
    async def open_detail(self, session_id: str) -> None:
        agent = await self.data_source.fetch_agent(session_id)
        if agent is not None:
            self.push_screen(DetailScreen(agent))

    def action_show_history(self) -> None:
        self.open_history()

    @work(group="history", exclusive=True)
    async def open_history(self) -> None:
        self.push_screen(HistoryScreen(await self.data_source.fetch_history()))

    def action_show_doctor(self) -> None:
        self.open_doctor()

    @work(group="doctor", exclusive=True)
    async def open_doctor(self) -> None:
        self.push_screen(DoctorScreen(await self.data_source.fetch_doctor()))
