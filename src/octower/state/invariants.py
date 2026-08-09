"""Safety guard functions implementing INV-001 through INV-010 (§4)."""

from __future__ import annotations

from dataclasses import dataclass

from octower.models import CompletionEvidence, SessionEvidence


@dataclass(frozen=True, slots=True)
class GuardResult:
    """A passed guard permits the guarded operation; failure explains its block."""

    passed: bool
    reason: str


def inv_001_done_first(completion: CompletionEvidence) -> GuardResult:
    """Block stall handling after terminal evidence (INV-001, §10)."""
    return GuardResult(not completion.terminal, "session is DONE" if completion.terminal else "not terminal")


def inv_002_same_session(session_id: str, target_session_id: str) -> GuardResult:
    """Require same-session identity for future normal recovery (INV-002)."""
    return GuardResult(session_id == target_session_id, "same session" if session_id == target_session_id else "session ID changed")


def inv_003_retry_protected(evidence: SessionEvidence) -> GuardResult:
    """Block nudge/abort while provider retry is observed (INV-003)."""
    return GuardResult(evidence.status != "retry", "provider retry is protected" if evidence.status == "retry" else "not retrying")


def inv_004_tools_protected(evidence: SessionEvidence) -> GuardResult:
    """Block abort when any tool is pending or running (INV-004)."""
    active = any(state in {"pending", "running"} for state in evidence.tool_states)
    return GuardResult(not active, "active tool is protected" if active else "no active tool")


def inv_005_human_wait_protected(evidence: SessionEvidence) -> GuardResult:
    """Block nudge/abort for permission or question waits (INV-005)."""
    return GuardResult(not evidence.human_waiting, "human input wait is protected" if evidence.human_waiting else "not waiting for human")


def inv_006_descendant_protected(evidence: SessionEvidence) -> GuardResult:
    """Block declaring a parent stalled while a descendant is active (INV-006)."""
    return GuardResult(not evidence.active_descendant, "active descendant protects parent" if evidence.active_descendant else "no active descendant")


def inv_007_data_healthy(evidence: SessionEvidence) -> GuardResult:
    """Fail safe when API health or semantic observations are degraded (INV-007)."""
    healthy = evidence.api_healthy and evidence.semantic_data_complete and evidence.data_consistent
    return GuardResult(healthy, "semantic API data is healthy" if healthy else "semantic API data is degraded")


def inv_008_recovery_idempotent(evidence: SessionEvidence) -> GuardResult:
    """Block duplicate future recovery while one is already in progress (INV-008)."""
    return GuardResult(not evidence.recovery_in_progress, "no recovery in progress" if not evidence.recovery_in_progress else "recovery already in progress")


def inv_009_no_prompt_overlap(evidence: SessionEvidence) -> GuardResult:
    """Expose the future prompt-overlap guard without issuing prompts (INV-009)."""
    return GuardResult(evidence.status != "busy", "no active generation" if evidence.status != "busy" else "busy turn cannot accept overlapping prompt")


def inv_010_attempts_bounded(evidence: SessionEvidence, maximum: int) -> GuardResult:
    """Block automatic recovery after its configured bounded attempts (INV-010)."""
    passed = evidence.recovery_attempts < maximum
    return GuardResult(passed, "recovery attempts remain" if passed else "maximum recovery attempts reached")


def stall_guards(
    evidence: SessionEvidence, completion: CompletionEvidence, maximum_recovery_attempts: int
) -> tuple[GuardResult, ...]:
    """Return all Phase 2 stall-candidate guards; classifier consumes these (§4, §12)."""
    return (
        inv_001_done_first(completion),
        inv_003_retry_protected(evidence),
        inv_004_tools_protected(evidence),
        inv_005_human_wait_protected(evidence),
        inv_006_descendant_protected(evidence),
        inv_007_data_healthy(evidence),
        inv_008_recovery_idempotent(evidence),
        inv_010_attempts_bounded(evidence, maximum_recovery_attempts),
    )
