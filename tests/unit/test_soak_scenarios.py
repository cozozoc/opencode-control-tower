from __future__ import annotations

from pathlib import Path

import pytest

from octower.models import AgentState
from octower.soak.scenarios import REQUIRED_SCENARIOS, run_scenario


@pytest.mark.parametrize("name", REQUIRED_SCENARIOS)
def test_required_scenario_has_zero_violations(name: str, tmp_path: Path) -> None:
    # Given / When
    result = run_scenario(name, tmp_path / name)

    # Then
    assert result.report.violations == ()
    assert result.report.false_aborts == 0


def test_cases_a_b_c_and_d_preserve_protected_or_completed_sessions(tmp_path: Path) -> None:
    # Given / When
    retry = run_scenario("retry_protected", tmp_path / "a")
    tool = run_scenario("running_tool_protected", tmp_path / "b")
    done = run_scenario("done_never_stalls", tmp_path / "c")
    idle = run_scenario("idle_unfinished_soft_resume", tmp_path / "d")

    # Then
    assert retry.report.aborts == 0
    assert tool.report.aborts == 0
    assert done.state_for("done-child") is AgentState.DONE
    assert idle.report.aborts == 0
    assert idle.report.resume_count == 1


def test_case_e_aborts_then_resumes_the_same_session(tmp_path: Path) -> None:
    # Given / When
    result = run_scenario("busy_hard_stall", tmp_path)

    # Then
    assert result.report.aborts == 1
    assert result.report.resume_count == 1
    assert result.report.stall_confirmations == 1
    assert result.state_for("hard-stall") is AgentState.RUNNING
    assert result.action_session_ids == ("hard-stall", "hard-stall")


def test_case_h_rehydrates_only_previously_active_work(tmp_path: Path) -> None:
    # Given / When
    result = run_scenario("backend_restart_rehydration", tmp_path)

    # Then
    assert result.report.backend_restarts == 1
    assert result.resumed_session_ids == ("active", "recovering")


def test_case_m_refuses_to_arm_automatic_recovery(tmp_path: Path) -> None:
    # Given / When
    result = run_scenario("omo_conflict_gate", tmp_path)

    # Then
    assert result.automatic_recovery_armed is False
    assert result.report.recovery_attempts == 0
