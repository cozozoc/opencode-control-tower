from conftest import evidence

from octower.models import AgentState, ConfirmationProgress, ThresholdConfig
from octower.state.classifier import AgentStateClassifier


def test_fake_clock_drives_five_ten_fifteen_minute_transitions(clock) -> None:
    classifier = AgentStateClassifier(clock)
    item = evidence()

    assert classifier.classify(item).state is AgentState.RUNNING
    clock.advance_minutes(5)
    assert classifier.classify(item).state is AgentState.SLOW
    clock.advance_minutes(5)
    assert classifier.classify(item).state is AgentState.SUSPECT
    clock.advance_minutes(5)
    assert classifier.classify(item).state is AgentState.STALL_CONFIRMING


def test_inv_001_done_never_becomes_stall_target_after_infinite_silence(clock) -> None:
    classifier = AgentStateClassifier(clock)
    completed = evidence(final_assistant_completed=True)
    clock.advance_minutes(1_000_000)

    result = classifier.classify(completed)

    assert result.state is AgentState.DONE
    assert result.completion.terminal is True


def test_inv_003_retry_is_waiting_and_never_stall_confirming(clock) -> None:
    classifier = AgentStateClassifier(clock)
    clock.advance_minutes(30)

    assert classifier.classify(evidence(status="retry")).state is AgentState.WAITING


def test_inv_004_long_running_tool_is_waiting_not_stalled(clock) -> None:
    classifier = AgentStateClassifier(clock)
    clock.advance_minutes(25)

    assert classifier.classify(evidence(status="busy", tool_states=("running",))).state is AgentState.WAITING


def test_inv_005_permission_or_question_wait_is_protected(clock) -> None:
    classifier = AgentStateClassifier(clock)
    clock.advance_minutes(20)

    assert classifier.classify(evidence(human_waiting=True)).state is AgentState.WAITING


def test_inv_006_active_descendant_protects_silent_parent(clock) -> None:
    classifier = AgentStateClassifier(clock)
    clock.advance_minutes(20)

    assert classifier.classify(evidence(active_descendant=True)).state is AgentState.WAITING


def test_inv_007_missing_or_inconsistent_data_fails_safe(clock) -> None:
    classifier = AgentStateClassifier(clock)
    clock.advance_minutes(20)

    assert classifier.classify(evidence(semantic_data_complete=False)).state is AgentState.DEGRADED
    assert classifier.classify(evidence(data_consistent=False)).state is AgentState.DEGRADED
    assert classifier.classify(evidence(api_healthy=False)).state is AgentState.DEGRADED
    assert classifier.classify(evidence(status=None)).state is AgentState.WAITING


def test_global_backend_recovery_and_failed_recovery_states(clock) -> None:
    classifier = AgentStateClassifier(clock)

    assert classifier.classify(evidence(backend_available=False)).state is AgentState.BACKEND_DOWN
    assert classifier.classify(evidence(recovery_in_progress=True)).state is AgentState.RECOVERING
    assert classifier.classify(evidence(recovery_attempts=2)).state is AgentState.FAILED_RECOVERY


def test_recovery_requires_post_recovery_activity_before_running(clock) -> None:
    classifier = AgentStateClassifier(clock)
    clock.advance(10)

    awaiting = evidence(last_semantic_activity=0, recovery_started_at=5)
    resumed = evidence(last_semantic_activity=6, recovery_started_at=5)

    assert classifier.classify(awaiting, AgentState.RECOVERING).state is AgentState.RECOVERING
    assert classifier.classify(resumed, AgentState.RECOVERING).state is AgentState.RUNNING


def test_confirmation_rechecks_protections_and_requires_window_and_samples(clock) -> None:
    config = ThresholdConfig(stall_confirm_seconds=60, stall_confirm_samples=4)
    classifier = AgentStateClassifier(clock, config)
    clock.advance_minutes(15)
    candidate = evidence(status="busy")

    first = classifier.confirm_candidate(candidate, None)
    assert first.state is AgentState.STALL_CONFIRMING
    assert first.confirmation == ConfirmationProgress(900, 1)
    assert classifier.confirm_candidate(evidence(status="retry"), first.confirmation).state is AgentState.WAITING

    progress = first.confirmation
    assert progress is not None
    for _ in range(2):
        clock.advance(20)
        progress = classifier.confirm_candidate(candidate, progress).confirmation
        assert progress is not None
    clock.advance(20)
    confirmed = classifier.confirm_candidate(candidate, progress)

    assert confirmed.state is AgentState.RECOVERING
    assert confirmed.confirmation is not None and confirmed.confirmation.samples == 4
