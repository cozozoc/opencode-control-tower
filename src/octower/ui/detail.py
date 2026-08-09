"""Large and full-screen selected-agent detail for handoff §26."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from octower.ui.data_source import AgentSnapshot


class DetailScreen(Screen[None]):
    """Focused output and state history for one stable session selection."""

    BINDINGS = [("f", "close_focus", "Board"), ("escape", "close_focus", "Board")]

    def __init__(self, agent: AgentSnapshot) -> None:
        super().__init__(id="detail-screen")
        self.agent = agent

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="focus-detail"):
            yield Static("FOCUS MODE", classes="section-title")
            yield Static(self.agent.title, id="focus-heading")
            yield Static(
                f"{self.agent.session_id}  ·  {self.agent.state.value.upper()}",
                id="focus-state",
            )
            yield Static(self._state_history(), id="focus-state-history")
            yield Static(self._output_history(), id="focus-output")
        yield Footer()

    def action_close_focus(self) -> None:
        self.app.pop_screen()

    def _state_history(self) -> str:
        states = "  >  ".join(state.value.upper() for state in self.agent.state_history)
        return f"STATE HISTORY\n{states or self.agent.state.value.upper()}"

    def _output_history(self) -> str:
        history = self.agent.output_history or (self.agent.output_preview,)
        return "OUTPUT HISTORY\n\n" + "\n".join(history)
