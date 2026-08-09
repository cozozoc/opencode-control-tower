from conftest import evidence

from octower.state.completion import classify_completion


def test_completion_requires_positive_terminal_evidence_and_todo_may_be_absent() -> None:
    result = classify_completion(evidence(final_assistant_completed=True))

    assert result.terminal is True
    assert result.confidence == "high"


def test_completion_rejects_busy_tool_todo_and_intermediate_response() -> None:
    result = classify_completion(
        evidence(
            status="busy",
            tool_states=("running",),
            todo_states=("in_progress",),
            final_assistant_completed=True,
            final_assistant_intermediate=True,
        )
    )

    assert result.terminal is False
    assert "session status is busy" in result.reasons
    assert "tool is pending or running" in result.reasons
    assert "todo is pending or in progress" in result.reasons
    assert "final assistant step is intermediate tool calls" in result.reasons
