from __future__ import annotations

import json
from pathlib import Path

import pytest

from octower.omo.policy import (
    RECOMMENDED_STALE_TIMEOUT_MS,
    OmoPolicyConflict,
    build_patch_suggestion,
    evaluate_policy_conflict,
)


@pytest.mark.parametrize("timeout_ms", [180000, 600000])
def test_timeout_below_fifteen_minutes_is_critical(timeout_ms: int) -> None:
    assert evaluate_policy_conflict(timeout_ms) is OmoPolicyConflict.CONFLICT_CRITICAL


def test_thirty_minute_timeout_does_not_race_guardian() -> None:
    assert evaluate_policy_conflict(1800000) is OmoPolicyConflict.OK


def test_patch_suggestion_targets_effective_config_without_mutating_it() -> None:
    target = Path("C:/Users/tester/.omo/omo.jsonc")

    suggestion = build_patch_suggestion(target)
    snippet = json.loads(suggestion.json_snippet)

    assert suggestion.target_path == target
    assert suggestion.stale_timeout_ms == RECOMMENDED_STALE_TIMEOUT_MS == 1800000
    assert snippet == {"background_task": {"staleTimeoutMs": 1800000}}
    assert suggestion.requires_explicit_operator_action is True
    assert suggestion.instruction == "do not silently overwrite user config"
