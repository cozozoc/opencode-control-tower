"""Guardian/OmO stale-timeout conflict policy from §21 and Case M."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Final, assert_never

from octower.omo.config import ResolvedStaleTimeout


GUARDIAN_STALL_THRESHOLD_MS: Final = 900_000
RECOMMENDED_STALE_TIMEOUT_MS: Final = 1_800_000
NO_MUTATION_INSTRUCTION: Final = "do not silently overwrite user config"


class OmoPolicyConflict(str, Enum):
    """Whether OmO can interrupt a task before Guardian's hard-stall threshold."""

    OK = "ok"
    CONFLICT_CRITICAL = "conflict_critical"


OmOPolicyConflict = OmoPolicyConflict


@dataclass(frozen=True, slots=True)
class OmoPolicyEvaluation:
    """Case M startup gate and the Guardian threshold that produced it."""

    conflict: OmoPolicyConflict
    automatic_recovery_allowed: bool
    guardian_stall_threshold_ms: int = GUARDIAN_STALL_THRESHOLD_MS


@dataclass(frozen=True, slots=True)
class OmoConfigPatchSuggestion:
    """Operator-applied patch data; this type has no write capability."""

    target_path: Path
    stale_timeout_ms: int
    json_snippet: str
    mutates_config: bool
    operator_action_required: bool
    instruction: str

    @property
    def requires_explicit_operator_action(self) -> bool:
        return self.operator_action_required


def evaluate_policy_conflict(stale_timeout_ms: int) -> OmoPolicyConflict:
    """Classify values below 15 minutes as the critical Case M conflict."""
    if stale_timeout_ms < GUARDIAN_STALL_THRESHOLD_MS:
        return OmoPolicyConflict.CONFLICT_CRITICAL
    return OmoPolicyConflict.OK


def evaluate_policy(stale_timeout_ms: int) -> OmoPolicyEvaluation:
    """Evaluate startup arming without performing recovery or config actions."""
    conflict = evaluate_policy_conflict(stale_timeout_ms)
    return OmoPolicyEvaluation(
        conflict,
        automatic_recovery_allowed=conflict is OmoPolicyConflict.OK,
    )


def build_patch_suggestion(
    target: Path | ResolvedStaleTimeout,
    home: Path | None = None,
) -> OmoConfigPatchSuggestion:
    """Generate an explicit 30-minute patch suggestion without touching the target."""
    match target:
        case Path() as path:
            target_path = path
        case ResolvedStaleTimeout(config_path=config_path):
            target_path = config_path or (home or Path.home()) / ".omo" / "omo.jsonc"
        case unreachable:
            assert_never(unreachable)
    snippet = json.dumps(
        {"background_task": {"staleTimeoutMs": RECOMMENDED_STALE_TIMEOUT_MS}},
        separators=(",", ":"),
    )
    return OmoConfigPatchSuggestion(
        target_path,
        RECOMMENDED_STALE_TIMEOUT_MS,
        snippet,
        False,
        True,
        NO_MUTATION_INSTRUCTION,
    )
