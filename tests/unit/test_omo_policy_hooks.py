from __future__ import annotations

from pathlib import Path

import pytest

from octower.omo.config import ResolvedStaleTimeout, StaleTimeoutSource
from octower.omo.hooks import OmOTaskState, is_terminal_task_state
from octower.omo.policy import (
    GUARDIAN_STALL_THRESHOLD_MS,
    RECOMMENDED_STALE_TIMEOUT_MS,
    OmOPolicyConflict,
    build_patch_suggestion,
    evaluate_policy,
)


@pytest.mark.parametrize("timeout_ms", [180000, 600000, 899999])
def test_timeout_below_guardian_threshold_is_critical(timeout_ms: int) -> None:
    evaluation = evaluate_policy(timeout_ms)

    assert evaluation.conflict is OmOPolicyConflict.CONFLICT_CRITICAL
    assert evaluation.automatic_recovery_allowed is False
    assert evaluation.guardian_stall_threshold_ms == GUARDIAN_STALL_THRESHOLD_MS


@pytest.mark.parametrize("timeout_ms", [900000, 1800000])
def test_timeout_at_or_above_guardian_threshold_is_ok(timeout_ms: int) -> None:
    evaluation = evaluate_policy(timeout_ms)

    assert evaluation.conflict is OmOPolicyConflict.OK
    assert evaluation.automatic_recovery_allowed is True


def test_patch_suggestion_targets_detected_config_and_never_mutates() -> None:
    path = Path("C:/work/project/.omo/omo.jsonc")
    resolution = ResolvedStaleTimeout(
        value_ms=180000,
        source=StaleTimeoutSource.DEFAULT,
        config_path=path,
        raw_config_available=True,
    )

    suggestion = build_patch_suggestion(resolution, Path("C:/Users/tester"))

    assert suggestion.target_path == path
    assert suggestion.stale_timeout_ms == RECOMMENDED_STALE_TIMEOUT_MS
    assert suggestion.json_snippet == '{"background_task":{"staleTimeoutMs":1800000}}'
    assert suggestion.mutates_config is False
    assert suggestion.operator_action_required is True


def test_patch_suggestion_uses_modern_path_when_config_is_missing() -> None:
    home = Path("C:/Users/tester")
    resolution = ResolvedStaleTimeout(
        value_ms=180000,
        source=StaleTimeoutSource.DEFAULT,
        config_path=None,
        raw_config_available=False,
    )

    suggestion = build_patch_suggestion(resolution, home)

    assert suggestion.target_path == home / ".omo/omo.jsonc"


@pytest.mark.parametrize(
    ("state", "terminal"),
    [
        (OmOTaskState.RUNNING, False),
        (OmOTaskState.TERMINAL, True),
        (OmOTaskState.UNKNOWN, False),
    ],
)
def test_task_state_mapping_is_exhaustive(state: OmOTaskState, terminal: bool) -> None:
    assert is_terminal_task_state(state) is terminal
