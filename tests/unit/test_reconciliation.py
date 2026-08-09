from __future__ import annotations

import asyncio

import httpx

from octower.api.events import OpenCodeEvent, parse_sse_lines
from octower.api.opencode import OpenCodeClient
from octower.discovery.reconciliation import SessionReconciler
from octower.models import SessionNode


def test_reconciliation_adds_and_removes_children_and_flags_missing_root() -> None:
    state = {"sessions": [_session("root"), _session("child", "root")]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/session":
            return httpx.Response(200, json=state["sessions"])
        parent = request.url.path.split("/")[2]
        children = [item for item in state["sessions"] if item.get("parentID") == parent]
        return httpx.Response(200, json=children)

    reconciler = SessionReconciler("root", OpenCodeClient("http://opencode.test", transport=httpx.MockTransport(handler)))

    first = reconciler.reconcile()
    state["sessions"] = [_session("root")]
    second = reconciler.reconcile()
    state["sessions"] = []
    missing = reconciler.reconcile()

    assert "child" in first.added
    assert second.removed == ("child",)
    assert missing.root_exists is False
    assert missing.degraded is False


def test_reconciliation_marks_listing_failure_as_degraded_not_missing_root() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    result = SessionReconciler("root", OpenCodeClient("http://opencode.test", transport=httpx.MockTransport(handler))).reconcile()

    assert result.root_exists is None
    assert result.degraded is True


def test_created_event_adds_a_new_direct_child() -> None:
    reconciler = SessionReconciler("root", OpenCodeClient("http://opencode.test", transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))))
    reconciler.tree.add(SessionNode("root"))

    added = reconciler.handle_event(
        OpenCodeEvent("session.created", {"info": {"id": "child", "parentID": "root"}}, {})
    )

    assert added is True
    assert reconciler.tree.get("child") is not None


def test_sse_parser_yields_typed_event_from_synthetic_stream() -> None:
    async def lines():
        yield 'data: {"type":"session.created","properties":{"sessionID":"ses-child"}}'
        yield ""

    async def collect():
        return [event async for event in parse_sse_lines(lines())]

    events = asyncio.run(collect())

    assert events[0].type == "session.created"
    assert events[0].session_id == "ses-child"


def _session(session_id: str, parent_id: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {"id": session_id, "title": session_id, "directory": "C:/project"}
    if parent_id is not None:
        result["parentID"] = parent_id
    return result
