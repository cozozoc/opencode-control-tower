from conftest import evidence

from octower.state.completion import classify_completion
from octower.state.invariants import (
    inv_001_done_first,
    inv_002_same_session,
    inv_003_retry_protected,
    inv_004_tools_protected,
    inv_005_human_wait_protected,
    inv_006_descendant_protected,
    inv_007_data_healthy,
    inv_008_recovery_idempotent,
    inv_009_no_prompt_overlap,
    inv_010_attempts_bounded,
)


def test_inv_001_and_inv_002_return_failure_reason_when_safety_is_violated() -> None:
    done = classify_completion(evidence(final_assistant_completed=True))

    assert inv_001_done_first(done).passed is False
    assert inv_002_same_session("ses-a", "ses-b").passed is False


def test_inv_003_through_inv_010_expose_blocking_guard_results() -> None:
    retry = evidence(status="retry")
    tool = evidence(tool_states=("pending",))
    human = evidence(human_waiting=True)
    parent = evidence(active_descendant=True)
    degraded = evidence(data_consistent=False)
    recovering = evidence(recovery_in_progress=True)
    busy = evidence(status="busy")
    exhausted = evidence(recovery_attempts=2)

    assert inv_003_retry_protected(retry).passed is False
    assert inv_004_tools_protected(tool).passed is False
    assert inv_005_human_wait_protected(human).passed is False
    assert inv_006_descendant_protected(parent).passed is False
    assert inv_007_data_healthy(degraded).passed is False
    assert inv_008_recovery_idempotent(recovering).passed is False
    assert inv_009_no_prompt_overlap(busy).passed is False
    assert inv_010_attempts_bounded(exhausted, 2).passed is False
