"""DoctorReport rendering for handoff §21 and §27."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from octower.omo.doctor import DoctorReport


class DoctorScreen(Screen[None]):
    """Sectioned compatibility, integration, and environment status view."""

    BINDINGS = [("escape", "close", "Board"), ("x", "close", "Board")]

    def __init__(self, report: DoctorReport) -> None:
        super().__init__(id="doctor-screen")
        self.report = report

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("DOCTOR / STATUS", classes="view-title")
        yield Static(self._render_report(), id="doctor-report")
        yield Footer()

    def action_close(self) -> None:
        self.app.pop_screen()

    def _render_report(self) -> str:
        report = self.report
        config_path = str(report.omo_config_path) if report.omo_config_path else "not found"
        detected = "detected" if report.omo_detected else "not detected"
        return (
            "OPENCODE\n"
            f"  Version             {report.opencode_version or 'unknown'}\n"
            f"  API compatibility   {report.api_compatibility.value.upper()}\n"
            f"  Server health       {report.server_health.value.upper()}\n\n"
            "OMO INTEGRATION\n"
            f"  Installation        {detected}\n"
            f"  Version             {report.omo_version or 'unknown'}\n"
            f"  Config              {config_path}\n"
            f"  Stale timeout       {report.omo_stale_timeout_ms} ms\n"
            f"  Conflict            {report.omo_conflict.value.upper()}\n"
            f"  tmux                {report.tmux_integration.value.upper()}\n\n"
            "ENVIRONMENT\n"
            f"  Project             {report.project}\n"
            f"  Root session        {report.root_session_id}\n"
            f"  Python              {report.required_python_version}\n"
            f"  Textual             {report.required_textual_version}"
        )
