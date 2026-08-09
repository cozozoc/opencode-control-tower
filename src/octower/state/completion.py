"""Positive completion classifier; it must run before stall logic (INV-001, §10)."""

from __future__ import annotations

from octower.models import CompletionEvidence, SessionEvidence


_ACTIVE_TOOLS = frozenset({"pending", "running"})
_OPEN_TODOS = frozenset({"pending", "in_progress"})


def classify_completion(evidence: SessionEvidence) -> CompletionEvidence:
    """Return high-confidence DONE evidence only from positive terminal facts (§10)."""
    if evidence.adapter_terminal:
        return CompletionEvidence(True, "high", ("adapter reports terminal task state",))

    blockers: list[str] = []
    if not evidence.semantic_data_complete or not evidence.data_consistent:
        blockers.append("semantic data is incomplete or inconsistent")
    if evidence.status is None:
        blockers.append("session status is unavailable")
    elif evidence.status in {"busy", "retry"}:
        blockers.append(f"session status is {evidence.status}")
    if any(state in _ACTIVE_TOOLS for state in evidence.tool_states):
        blockers.append("tool is pending or running")
    if any(state in _OPEN_TODOS for state in evidence.todo_states):
        blockers.append("todo is pending or in progress")
    if evidence.unresolved_error:
        blockers.append("session has an unresolved error")
    if not evidence.final_assistant_completed:
        blockers.append("final assistant response is not complete")
    if evidence.final_assistant_intermediate:
        blockers.append("final assistant step is intermediate tool calls")
    if evidence.adapter_task_running:
        blockers.append("adapter reports task still running")

    if blockers:
        return CompletionEvidence(False, "low", tuple(blockers))
    return CompletionEvidence(
        True,
        "high",
        ("idle", "no active tools", "no open todos", "completed final assistant response"),
    )
