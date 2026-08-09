from __future__ import annotations

from pathlib import Path
from typing import assert_never

from octower.omo.config import ConfigValueSource, ResolvedStaleTimeout
from octower.omo.detection import OmoInstallation
from octower.omo.doctor import (
    DoctorContext,
    OpenCodeApiCompatibility,
    ServerHealth,
    TmuxIntegration,
    build_doctor_report,
)
from octower.omo.policy import OmoPolicyConflict
from octower.omo.task_state import OmoTaskState, map_task_state


class FakeDoctorSources:
    def opencode_version(self) -> str:
        return "1.18.15"

    def omo_installation(self) -> OmoInstallation:
        return OmoInstallation(True, "4.19.4", Path("C:/pkg/package.json"), None)

    def omo_stale_timeout(self) -> ResolvedStaleTimeout:
        return ResolvedStaleTimeout(
            value_ms=180000,
            source=ConfigValueSource.DEFAULT,
            config_path=Path("C:/Users/tester/.omo/omo.jsonc"),
            raw_config_available=True,
        )

    def tmux_integration(self) -> TmuxIntegration:
        return TmuxIntegration.DISABLED

    def server_health(self) -> ServerHealth:
        return ServerHealth.HEALTHY


def test_doctor_report_composes_all_section_21_fields_from_injected_sources() -> None:
    context = DoctorContext(Path("C:/work/project"), "ses-root")

    report = build_doctor_report(FakeDoctorSources(), context)

    assert report.opencode_version == "1.18.15"
    assert report.api_compatibility is OpenCodeApiCompatibility.SUPPORTED
    assert report.omo_detected is True
    assert report.omo_version == "4.19.4"
    assert report.omo_config_path == Path("C:/Users/tester/.omo/omo.jsonc")
    assert report.omo_stale_timeout_ms == 180000
    assert report.omo_conflict is OmoPolicyConflict.CONFLICT_CRITICAL
    assert report.tmux_integration is TmuxIntegration.DISABLED
    assert report.root_session_id == "ses-root"
    assert report.project == Path("C:/work/project")
    assert report.server_health is ServerHealth.HEALTHY
    assert report.required_python_version == ">=3.11"
    assert report.required_textual_version == "Phase 7 dependency not installed"


def test_task_state_mapping_is_exhaustive_and_never_wakes_omo_tasks() -> None:
    for state in OmoTaskState:
        evidence = map_task_state(state)
        match state:
            case OmoTaskState.RUNNING:
                assert evidence.running is True and evidence.terminal is False
            case OmoTaskState.TERMINAL:
                assert evidence.running is False and evidence.terminal is True
            case OmoTaskState.UNKNOWN:
                assert evidence.running is False and evidence.terminal is False
            case unreachable:
                assert_never(unreachable)
        assert evidence.wake_requested is False
