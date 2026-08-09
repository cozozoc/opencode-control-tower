from __future__ import annotations

from octower.soak.provider import (
    ActionKind,
    DeterministicProvider,
    HumanWaitKind,
    ManualClock,
    ScriptedEvent,
    SessionScript,
)


def test_provider_applies_timed_events_without_real_sleep() -> None:
    # Given
    clock = ManualClock()
    provider = DeterministicProvider(
        clock,
        (
            SessionScript(
                "child",
                "root",
                (
                    ScriptedEvent(0, status="busy"),
                    ScriptedEvent(600, status="retry", provider_retry=True),
                    ScriptedEvent(1200, status="idle", final_assistant_completed=True),
                ),
            ),
        ),
    )

    # When
    clock.advance(600)
    retry = provider.get_evidence("child")
    clock.advance(600)
    done = provider.get_evidence("child")

    # Then
    assert retry.status == "retry"
    assert retry.adapter_task_running is True
    assert done.final_assistant_completed is True


def test_provider_records_same_session_recovery_actions() -> None:
    # Given
    clock = ManualClock(901)
    provider = DeterministicProvider(
        clock,
        (SessionScript("stalled", None, (ScriptedEvent(0, status="busy"),)),),
    )

    # When
    aborted = provider.abort_session("stalled")
    resumed = provider.prompt_async("stalled", "resume")

    # Then
    assert aborted is True
    assert resumed is True
    assert tuple(action.kind for action in provider.actions) == (
        ActionKind.ABORT,
        ActionKind.PROMPT_ASYNC,
    )
    assert all(action.session_id == "stalled" for action in provider.actions)


def test_provider_maps_permission_and_question_waits_to_protected_evidence() -> None:
    # Given
    provider = DeterministicProvider(
        ManualClock(),
        (
            SessionScript(
                "permission", None, (ScriptedEvent(0, human_wait_kind=HumanWaitKind.PERMISSION),)
            ),
            SessionScript(
                "question", None, (ScriptedEvent(0, human_wait_kind=HumanWaitKind.QUESTION),)
            ),
        ),
    )

    # When
    permission = provider.get_evidence("permission")
    question = provider.get_evidence("question")

    # Then
    assert permission.human_waiting is True
    assert question.human_waiting is True
