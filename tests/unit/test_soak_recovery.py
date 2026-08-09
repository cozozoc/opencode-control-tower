from __future__ import annotations

from pathlib import Path

from octower.models import AgentState
from octower.soak.scenarios import run_scenario


def test_nested_descendant_protects_parent_and_parent_wakes_after_completion(
    tmp_path: Path,
) -> None:
    # Given / When
    result = run_scenario("nested_children", tmp_path)

    # Then
    assert result.report.discovered_sessions == 3
    assert result.report.parent_protection_events >= 1
    assert result.state_for("grandchild") is AgentState.DONE
    assert "parent" in result.resumed_session_ids


def test_guardian_restart_replays_journal_once(tmp_path: Path) -> None:
    # Given / When
    result = run_scenario("guardian_restart_journal_replay", tmp_path)

    # Then
    assert result.report.journal_replays == 1
    assert result.report.resume_count == 1
    assert result.state_for("replay-child") is AgentState.RUNNING


def test_bounded_attempts_end_in_failed_recovery(tmp_path: Path) -> None:
    # Given / When
    result = run_scenario("bounded_attempts_failed", tmp_path)

    # Then
    assert result.state_for("never-recovers") is AgentState.FAILED_RECOVERY
    assert result.report.recovery_attempts == 2
    assert result.report.resume_count == 2


def test_human_wait_never_nudges_or_aborts(tmp_path: Path) -> None:
    # Given / When
    result = run_scenario("human_wait_protected", tmp_path)

    # Then
    assert result.state_for("human-wait") is AgentState.WAITING
    assert result.report.resume_count == 0
    assert result.report.aborts == 0
