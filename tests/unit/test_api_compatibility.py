from __future__ import annotations

import httpx

from octower.api.compatibility import OpenCodeCompatibility
from octower.api.opencode import OpenCodeClient
from octower.models import SessionEvidence
from octower.state.completion import classify_completion


def test_empty_status_is_advisory_and_cannot_infer_terminal_or_stall() -> None:
    client = OpenCodeClient(
        "http://opencode.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )
    compatibility = OpenCodeCompatibility(client)
    positive_evidence = SessionEvidence(
        session_id="ses-1", status="idle", last_semantic_activity=1.0, final_assistant_completed=True
    )

    assert compatibility.session_status() == {}
    assert compatibility.status_enrichment("ses-1") is None
    assert classify_completion(positive_evidence).terminal is True


def test_stale_status_does_not_mutate_positive_completion_evidence() -> None:
    client = OpenCodeClient(
        "http://opencode.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ses-1": {"type": "busy"}})
        ),
    )
    compatibility = OpenCodeCompatibility(client)
    evidence = SessionEvidence(
        session_id="ses-1", status="idle", last_semantic_activity=1.0, final_assistant_completed=True
    )

    assert compatibility.status_enrichment("ses-1").type == "busy"
    assert classify_completion(evidence).terminal is True
