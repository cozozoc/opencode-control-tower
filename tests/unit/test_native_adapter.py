from __future__ import annotations

import httpx

from octower.adapters.native_opencode import NativeOpenCodeAdapter
from octower.api.opencode import OpenCodeClient
from octower.models import AgentState
from octower.state.classifier import AgentStateClassifier
from octower.state.completion import classify_completion


def test_adapter_maps_completed_assistant_to_high_confidence_terminal_evidence() -> None:
    adapter = NativeOpenCodeAdapter(_client("idle", [_completed_message()], []))

    evidence = adapter.get_evidence("ses-child")

    assert evidence.last_semantic_activity == 1_700_000_002.0
    assert evidence.todo_states == ()
    assert evidence.tool_states == ("completed",)
    assert classify_completion(evidence).terminal is True


def test_adapter_keeps_busy_session_without_messages_nonterminal() -> None:
    adapter = NativeOpenCodeAdapter(_client("busy", [], []))

    assert classify_completion(adapter.get_evidence("ses-child")).terminal is False


def test_adapter_inferrs_idle_from_empty_advisory_and_completed_latest_assistant() -> None:
    evidence = NativeOpenCodeAdapter(_client({}, [_completed_message()], [])).get_evidence("ses-child")

    assert evidence.status == "idle"
    assert classify_completion(evidence).terminal is True
    assert classify_completion(evidence).confidence == "high"


def test_adapter_keeps_unknown_advisory_nonterminal(clock) -> None:
    evidence = NativeOpenCodeAdapter(_client("unknown", [_completed_message()], [])).get_evidence("ses-child")

    assert evidence.status is None
    assert classify_completion(evidence).terminal is False
    assert AgentStateClassifier(clock).classify(evidence).state is AgentState.WAITING


def test_adapter_keeps_empty_advisory_without_completed_latest_message_waiting(clock) -> None:
    no_messages = NativeOpenCodeAdapter(_client({}, [], [])).get_evidence("ses-child")
    unfinished = NativeOpenCodeAdapter(_client({}, [_unfinished_message()], [])).get_evidence("ses-child")

    assert no_messages.status is None
    assert unfinished.status is None
    assert classify_completion(no_messages).terminal is False
    assert classify_completion(unfinished).terminal is False
    assert AgentStateClassifier(clock).classify(no_messages).state is AgentState.WAITING
    assert AgentStateClassifier(clock).classify(unfinished).state is AgentState.WAITING


def test_adapter_keeps_completed_assistant_followed_by_user_message_waiting(clock) -> None:
    messages = [_completed_message(), _user_message()]
    evidence = NativeOpenCodeAdapter(_client({}, messages, [])).get_evidence("ses-child")

    assert evidence.status is None
    assert evidence.final_assistant_completed is False
    assert classify_completion(evidence).terminal is False
    assert AgentStateClassifier(clock).classify(evidence).state is AgentState.WAITING


def test_adapter_protects_running_tool_from_terminal_classification() -> None:
    adapter = NativeOpenCodeAdapter(_client("idle", [_completed_message("running")], []))

    evidence = adapter.get_evidence("ses-child")

    assert evidence.tool_states == ("running",)
    assert classify_completion(evidence).terminal is False


def test_adapter_protects_parent_when_child_semantic_evidence_fails(clock) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/session/ses-child/message":
            return httpx.Response(503)
        payloads = {
            "/session/ses-parent/message": [],
            "/session/ses-parent/todo": [],
            "/session/ses-parent/children": [{"id": "ses-child"}],
            "/session/status": {"ses-parent": {"type": "idle"}},
        }
        return httpx.Response(200, json=payloads[request.url.path])

    parent = NativeOpenCodeAdapter(
        OpenCodeClient("http://opencode.test", transport=httpx.MockTransport(handler))
    ).get_evidence("ses-parent")
    clock.advance_minutes(20)

    assert parent.active_descendant is True
    assert AgentStateClassifier(clock).classify(parent).state is AgentState.WAITING


def _client(status: str | dict[str, object], messages: list[dict[str, object]], todos: list[dict[str, object]]) -> OpenCodeClient:
    def handler(request: httpx.Request) -> httpx.Response:
        payloads = {
            "/session/ses-child/message": messages,
            "/session/ses-child/todo": todos,
            "/session/ses-child/children": [],
            "/session/status": status if isinstance(status, dict) else {"ses-child": {"type": status}},
        }
        return httpx.Response(200, json=payloads[request.url.path])

    return OpenCodeClient("http://opencode.test", transport=httpx.MockTransport(handler))


def _completed_message(tool_state: str = "completed") -> dict[str, object]:
    return {
        "info": {
            "id": "msg-1",
            "role": "assistant",
            "time": {"created": 1_700_000_001_000, "completed": 1_700_000_002_000},
        },
        "parts": [{"type": "tool", "state": {"status": tool_state}}],
    }


def _unfinished_message() -> dict[str, object]:
    return {
        "info": {"id": "msg-1", "role": "assistant", "time": {"created": 1_700_000_001_000}},
        "parts": [],
    }


def _user_message() -> dict[str, object]:
    return {
        "info": {"id": "msg-2", "role": "user", "time": {"created": 1_700_000_003_000}},
        "parts": [{"type": "text", "text": "continue"}],
    }
