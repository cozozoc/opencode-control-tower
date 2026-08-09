from __future__ import annotations

from pathlib import Path

from octower.models import AgentState
from octower.soak.harness import SoakHarness
from octower.soak.provider import (
    ActionKind,
    DeterministicProvider,
    ManualClock,
    ScriptedEvent,
    SessionScript,
)
from octower.soak.scenarios import run_scenario


def test_inv_002_and_009_hard_recovery_aborts_before_same_session_prompt(
    tmp_path: Path,
) -> None:
    # Given / When
    result = run_scenario("busy_hard_stall", tmp_path)

    # Then
    assert tuple(action.kind for action in result.actions) == (
        ActionKind.ABORT,
        ActionKind.PROMPT_ASYNC,
    )
    assert result.action_session_ids == ("hard-stall", "hard-stall")


def test_inv_007_degraded_semantic_reads_fail_safe(tmp_path: Path) -> None:
    # Given
    clock = ManualClock()
    provider = DeterministicProvider(
        clock,
        (
            SessionScript("root", None, (ScriptedEvent(0, provider_retry=True),)),
            SessionScript(
                "degraded",
                "root",
                (
                    ScriptedEvent(
                        0,
                        status="busy",
                        api_healthy=False,
                        semantic_data_complete=False,
                        data_consistent=False,
                    ),
                ),
            ),
        ),
    )
    harness = SoakHarness("root", provider, tmp_path / "journal.jsonl")

    # When
    harness.advance_and_sample(1_000)
    result = harness.result("degraded")

    # Then
    assert result.state_for("degraded") is AgentState.DEGRADED
    assert result.actions == ()


def test_case_d_records_suspect_before_recovering(tmp_path: Path) -> None:
    # Given / When
    result = run_scenario("idle_unfinished_soft_resume", tmp_path)

    # Then
    states = tuple(
        transition.current
        for transition in result.report.metrics.transitions
        if transition.session_id == "idle-child"
    )
    assert states[:2] == (AgentState.SUSPECT, AgentState.RECOVERING)
