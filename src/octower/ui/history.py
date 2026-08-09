"""Recent recovery journal activity screen for handoff §27."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from octower.recovery.journal import RecoveryRecord


class HistoryScreen(Screen[None]):
    """Read-only recent recovery transaction timeline."""

    BINDINGS = [("escape", "close", "Board"), ("h", "close", "Board")]

    def __init__(self, records: tuple[RecoveryRecord, ...]) -> None:
        super().__init__(id="history-screen")
        self.records = records

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("RECOVERY JOURNAL", classes="view-title")
        yield Static(self._render_records(), id="history-list")
        yield Footer()

    def action_close(self) -> None:
        self.app.pop_screen()

    def _render_records(self) -> str:
        if not self.records:
            return "No recovery activity recorded."
        rows = []
        for record in reversed(self.records[-100:]):
            rows.append(
                f"{record.created_at:>10.1f}  {record.session_id:<24}  "
                f"{record.phase.value:<24}  attempt {record.attempt}\n"
                f"            {record.reason}  ·  {record.adapter}"
            )
        return "\n\n".join(rows)
