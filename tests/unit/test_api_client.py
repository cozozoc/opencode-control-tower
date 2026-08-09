from __future__ import annotations

import httpx
import json
import pytest

from octower.api.opencode import NotFound, OpenCodeClient, ServerUnavailable


def make_client(handler) -> OpenCodeClient:
    return OpenCodeClient("http://opencode.test", transport=httpx.MockTransport(handler))


def test_client_parses_verified_11815_endpoint_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        responses = {
            "/global/health": {"healthy": True, "version": "1.18.15"},
            "/session": [_session("root"), _session("child", "root")],
            "/session/root": _session("root"),
            "/session/root/children": [_session("child", "root")],
            "/session/root/todo": [{"content": "verify", "status": "in_progress"}],
            "/session/root/message": [_message()],
        }
        if request.url.path == "/session/root/abort":
            return httpx.Response(200, json=True)
        if request.url.path == "/session/root/prompt_async":
            assert json.loads(request.content) == {
                "parts": [{"type": "text", "text": "continue"}],
                "messageID": "msg-2",
                "model": {"providerID": "provider", "modelID": "model"},
            }
            return httpx.Response(204)
        return httpx.Response(200, json=responses[request.url.path])

    client = make_client(handler)

    assert client.health().version == "1.18.15"
    assert [session.parent_id for session in client.list_sessions()] == [None, "root"]
    assert client.get_session("root").title == "Root"
    assert client.get_children("root")[0].id == "child"
    assert client.get_todo("root")[0].status == "in_progress"
    assert client.get_messages("root")[0].role == "assistant"
    assert client.abort("root") is True
    assert client.prompt_async(
        "root", "continue", message_id="msg-2", model={"providerID": "provider", "modelID": "model"}
    ) is True


def test_client_maps_not_found_and_timeout_to_typed_errors() -> None:
    missing = make_client(lambda request: httpx.Response(404))

    with pytest.raises(NotFound):
        missing.get_session("gone")

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ServerUnavailable):
        make_client(timeout).health()


def _session(session_id: str, parent_id: str | None = None) -> dict[str, object]:
    data: dict[str, object] = {
        "id": session_id,
        "directory": "C:/project",
        "title": "Root" if session_id == "root" else "Child",
        "time": {"created": 1_000},
    }
    if parent_id is not None:
        data["parentID"] = parent_id
    return data


def _message() -> dict[str, object]:
    return {
        "info": {"id": "msg-1", "role": "assistant", "time": {"created": 1_000, "completed": 2_000}},
        "parts": [{"type": "text", "text": "finished"}],
    }
