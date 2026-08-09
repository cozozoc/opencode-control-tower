"""Native OpenCode implementation of Phase 3 recovery and parent-wake actions (§7.2)."""

from __future__ import annotations

from octower.api.compatibility import OpenCodeCompatibility, SessionStatus
from octower.api.events import OpenCodeEvent
from octower.api.opencode import Message, OpenCodeClient, OpenCodeError
from octower.models import SessionEvidence
from octower.state.completion import classify_completion


class NativeOpenCodeAdapter:
    """Translate only verified OpenCode API data into conservative runtime evidence."""

    def __init__(self, client: OpenCodeClient, compatibility: OpenCodeCompatibility | None = None) -> None:
        self._client = client
        self._compatibility = compatibility or OpenCodeCompatibility(client)
        self._human_waiting: set[str] = set()
        self._unresolved_errors: set[str] = set()

    def abort_session(self, session_id: str) -> bool:
        """Abort one current turn while preserving its OpenCode session ID (§13)."""
        try:
            return self._client.abort(session_id)
        except OpenCodeError:
            return False

    def prompt_async(self, session_id: str, text: str) -> bool:
        """Send an accepted same-session continuation request (§7.2)."""
        try:
            return self._client.prompt_async(session_id, text)
        except OpenCodeError:
            return False

    def validate_session(self, session_id: str) -> bool:
        """Confirm a preserved session still exists before continuation (§13.3)."""
        try:
            self._client.get_session(session_id)
        except OpenCodeError:
            return False
        return True

    def observe_event(self, event: OpenCodeEvent) -> None:
        """Retain permission/error observations as protective evidence between polls."""
        session_id = event.session_id
        if session_id is None:
            return
        if event.type.startswith("permission."):
            if event.type.endswith(("resolved", "replied", "deleted")):
                self._human_waiting.discard(session_id)
            else:
                self._human_waiting.add(session_id)
        if event.type == "session.error":
            self._unresolved_errors.add(session_id)

    def get_evidence(self, session_id: str) -> SessionEvidence:
        """Assemble positive completion and protection evidence from live API reads (§9-§10)."""
        try:
            messages = self._client.get_messages(session_id)
            todos = self._client.get_todo(session_id)
            children = self._client.get_children(session_id)
            advisory = self._compatibility.status_enrichment(session_id)
        except OpenCodeError:
            return SessionEvidence(
                session_id=session_id,
                status=None,
                last_semantic_activity=None,
                backend_available=False,
                api_healthy=False,
                semantic_data_complete=False,
                data_consistent=False,
            )
        child_evidence = tuple(self.get_evidence(child.id) for child in children)
        tool_states = tuple(state for message in messages for state in _part_states(message))
        todo_states = tuple(todo.status for todo in todos)
        latest_message = messages[-1] if messages else None
        final_completed = latest_message is not None and latest_message.role == "assistant" and _message_completed(latest_message)
        final_intermediate = latest_message is not None and latest_message.role == "assistant" and (
            not final_completed or any(state in {"pending", "running"} for state in _part_states(latest_message))
        )
        human_waiting = session_id in self._human_waiting or _pending_permission(messages)
        status = _status(
            advisory,
            final_completed=final_completed,
            tool_states=tool_states,
            todo_states=todo_states,
            unresolved_error=session_id in self._unresolved_errors,
            human_waiting=human_waiting,
        )
        active_descendant = any(
            child.status in {"busy", "retry"}
            or any(state in {"pending", "running"} for state in child.tool_states)
            or child.active_descendant
            or (
                not classify_completion(child).terminal
                and (
                    child.status is None
                    or not child.semantic_data_complete
                    or not child.data_consistent
                )
            )
            for child in child_evidence
        )
        return SessionEvidence(
            session_id=session_id,
            status=status,
            last_semantic_activity=_last_activity(messages),
            tool_states=tool_states,
            todo_states=todo_states,
            final_assistant_completed=final_completed,
            final_assistant_intermediate=final_intermediate,
            unresolved_error=session_id in self._unresolved_errors,
            human_waiting=human_waiting,
            active_descendant=active_descendant,
            adapter_task_running=False,
        )

    def is_terminal(self, session_id: str) -> bool:
        """Convenience for callers that need the Phase 2 positive completion result."""
        return classify_completion(self.get_evidence(session_id)).terminal


def _part_states(message: Message) -> tuple[str, ...]:
    states: list[str] = []
    for part in message.parts:
        value = part.get("state", part.get("status"))
        if isinstance(value, str):
            states.append(value)
        elif isinstance(value, dict) and isinstance(value.get("status"), str):
            states.append(value["status"])
    return tuple(states)


def _message_completed(message: Message) -> bool:
    return bool(message.time and message.time.get("completed") is not None)


def _status(
    advisory: SessionStatus | None,
    *,
    final_completed: bool,
    tool_states: tuple[str, ...],
    todo_states: tuple[str, ...],
    unresolved_error: bool,
    human_waiting: bool,
) -> str | None:
    if advisory is not None:
        return advisory.type if advisory.type in {"idle", "busy", "retry"} else None
    if (
        final_completed
        and not any(state in {"pending", "running"} for state in tool_states)
        and not any(state in {"pending", "in_progress"} for state in todo_states)
        and not unresolved_error
        and not human_waiting
    ):
        return "idle"
    return None


def _last_activity(messages: list[Message]) -> float | None:
    timestamps = [
        value
        for message in messages
        for value in _timestamps(message)
        if value is not None
    ]
    return max(timestamps, default=None)


def _timestamps(message: Message) -> tuple[float | None, ...]:
    values: list[float | None] = []
    for time in (message.time, *(part.get("time") for part in message.parts)):
        if isinstance(time, dict):
            for key in ("created", "completed"):
                value = time.get(key)
                if isinstance(value, (int, float)):
                    values.append(float(value) / 1000 if value > 100_000_000_000 else float(value))
    return tuple(values)


def _pending_permission(messages: list[Message]) -> bool:
    for message in messages:
        for part in message.parts:
            kind = str(part.get("type", ""))
            if "permission" in kind and any(state in {"pending", "running"} for state in _part_states(Message("", "", parts=(part,)))):
                return True
    return False
