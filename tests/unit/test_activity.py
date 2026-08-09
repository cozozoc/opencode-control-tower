from octower.state.activity import SemanticActivityTracker


def test_visual_churn_does_not_count_as_semantic_activity(clock) -> None:
    tracker = SemanticActivityTracker(clock)

    assert tracker.observe("spinner", "frame-1") is None
    clock.advance(10)
    assert tracker.observe("cursor", "on") is None
    assert tracker.last_activity is None
    assert tracker.observe("refresh", "poll-2") is None
    assert tracker.last_activity is None


def test_tool_transition_and_message_completion_count_as_activity(clock) -> None:
    tracker = SemanticActivityTracker(clock)

    tool = tracker.observe("tool_transition", "bash:running")
    clock.advance(3)
    message = tracker.observe("message_completed", "msg-42")

    assert tool is not None and tool.occurred_at == 0
    assert message is not None and message.occurred_at == 3
    assert tracker.last_activity == 3


def test_unchanged_semantic_poll_is_not_new_activity(clock) -> None:
    tracker = SemanticActivityTracker(clock)
    tracker.observe("assistant_text_updated", "same-content")
    clock.advance(60)

    assert tracker.observe("assistant_text_updated", "same-content") is None
    assert tracker.last_activity == 0
