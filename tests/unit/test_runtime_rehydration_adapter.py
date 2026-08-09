from __future__ import annotations

from pathlib import Path

import anyio
import httpx

from octower.api.opencode import OpenCodeClient
from octower.discovery.reconciliation import SessionReconciler
from octower.models import AgentState
from octower.recovery.journal import RecoveryJournal, RecoveryPhase, RecoveryRecord
from octower.state.classifier import AgentStateClassifier
from octower.supervisor.rehydration import RootRestoreState


class FixedClock:
    def now(self) -> float:
        return 100.0


def test_rehydration_composes_live_api_journal_classifier_and_resume(tmp_path: Path) -> None:
    from octower.runtime.rehydration_adapter import RehydrationAdapter

    resumed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST":
            resumed.append(path.split("/")[2])
            return httpx.Response(204, request=request)
        if path == "/session":
            return httpx.Response(200, json=[{"id": "root"}, {"id": "child", "parentID": "root"}])
        if path == "/session/root/children":
            return httpx.Response(200, json=[{"id": "child", "parentID": "root"}])
        if path.endswith("/message"):
            return httpx.Response(
                200,
                json=[{"info": {"id": "message-1", "role": "user", "time": {"created": 95.0}}}],
            )
        if path.endswith("/children") or path.endswith("/todo"):
            return httpx.Response(200, json=[])
        if path == "/session/status":
            return httpx.Response(200, json={"child": {"type": "busy"}})
        return httpx.Response(404, request=request)

    journal = RecoveryJournal(tmp_path / "recovery.jsonl")
    journal.append(
        RecoveryRecord(
            recovery_id="recovery-1",
            session_id="child",
            root_session_id="root",
            parent_id="root",
            reason="backend restart",
            phase=RecoveryPhase.RECOVERING,
            attempt=1,
            created_at=90.0,
            last_activity_before=80.0,
            adapter="native",
        )
    )
    transport = httpx.MockTransport(handler)
    client = OpenCodeClient("http://127.0.0.1:43123", transport=transport)
    adapter = RehydrationAdapter(
        client,
        SessionReconciler("root", client),
        AgentStateClassifier(FixedClock()),
        journal,
        "root",
    )

    async def scenario() -> None:
        sessions = await adapter.reenumerate_sessions()
        assert sessions == ("root", "child")
        assert await adapter.restore_root("root", sessions) is RootRestoreState.READY
        recovering = await adapter.reload_journal()
        assert recovering == ("child",)
        classified = await adapter.reclassify(sessions, recovering)
        child = next(item for item in classified if item.session_id == "child")
        assert child.prior_state is AgentState.RECOVERING
        assert child.current_state is AgentState.RECOVERING
        assert child.unfinished is True
        await adapter.resume("child")

    try:
        anyio.run(scenario)
    finally:
        client.close()

    assert resumed == ["child"]
