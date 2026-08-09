"""Small HTTP client for the verified OpenCode 1.18.15 API (§2, §7.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class OpenCodeError(RuntimeError):
    """Base error for a rejected or unavailable OpenCode control API."""


class NotFound(OpenCodeError):
    """The requested OpenCode resource no longer exists."""


class ServerUnavailable(OpenCodeError):
    """The local OpenCode server cannot be contacted safely."""


@dataclass(frozen=True, slots=True)
class Health:
    """Health payload reported by ``GET /global/health`` (§15)."""

    healthy: bool
    version: str | None


@dataclass(frozen=True, slots=True)
class Session:
    """Minimal persisted session representation returned by ``/session`` (§2.3)."""

    id: str
    directory: str = ""
    title: str = ""
    time: dict[str, Any] | None = None
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class Todo:
    """Minimal task entry returned by ``GET /session/:id/todo`` (§2.5)."""

    content: str
    status: str


@dataclass(frozen=True, slots=True)
class Message:
    """Visible message and its parts returned by ``GET /session/:id/message`` (§10)."""

    id: str
    role: str
    time: dict[str, Any] | None = None
    parts: tuple[dict[str, Any], ...] = ()


class OpenCodeClient:
    """Synchronous OpenCode client with transport injection for contract tests."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float | httpx.Timeout = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(transport=transport, timeout=timeout)

    def close(self) -> None:
        """Close a client created by this wrapper."""
        if self._owns_client:
            self._client.close()

    def health(self) -> Health:
        """Read backend availability and installed OpenCode version (§15)."""
        data = self._get_json("/global/health")
        return Health(bool(data.get("healthy")), _optional_string(data.get("version")))

    def list_sessions(self) -> list[Session]:
        """List persisted sessions without assuming a fixed fleet size (R1)."""
        return [_session(item) for item in self._get_json("/session")]

    def get_session(self, session_id: str) -> Session:
        """Fetch one existing session for same-session validation (§13.3)."""
        return _session(self._get_json(f"/session/{session_id}"))

    def get_children(self, session_id: str) -> list[Session]:
        """Fetch direct child sessions for recursive discovery (§8)."""
        return [_session(item) for item in self._get_json(f"/session/{session_id}/children")]

    def get_todo(self, session_id: str) -> list[Todo]:
        """Fetch the optional task state; an empty list is normal (§10)."""
        return [_todo(item) for item in self._get_json(f"/session/{session_id}/todo")]

    def get_messages(self, session_id: str) -> list[Message]:
        """Fetch visible message and part state used as semantic evidence (§9-§10)."""
        return [_message(item) for item in self._get_json(f"/session/{session_id}/message")]

    def abort(self, session_id: str) -> bool:
        """Abort only a current turn of the preserved session (§13.2)."""
        response = self._request("POST", f"/session/{session_id}/abort")
        return bool(response.json())

    def prompt_async(
        self,
        session_id: str,
        text: str,
        *,
        message_id: str | None = None,
        model: dict[str, Any] | None = None,
    ) -> bool:
        """Request a same-session continuation; 204 is acceptance, not success (§13.4)."""
        payload: dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        if message_id is not None:
            payload["messageID"] = message_id
        if model is not None:
            payload["model"] = model
        return self._request("POST", f"/session/{session_id}/prompt_async", json=payload).status_code == 204

    def get_session_status(self) -> dict[str, Any]:
        """Return raw advisory status data; callers must use the compatibility layer (§2.4)."""
        data = self._get_json("/session/status")
        if not isinstance(data, dict):
            raise OpenCodeError("OpenCode returned a non-object session status payload")
        return data

    def _get_json(self, path: str) -> Any:
        return self._request("GET", path).json()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, f"{self.base_url}{path}", **kwargs)
        except httpx.TimeoutException as error:
            raise ServerUnavailable("OpenCode request timed out") from error
        except httpx.HTTPError as error:
            raise ServerUnavailable("OpenCode server is unavailable") from error
        if response.status_code == 404:
            raise NotFound(f"OpenCode resource not found: {path}")
        if response.status_code >= 500:
            raise ServerUnavailable(f"OpenCode server failed with HTTP {response.status_code}")
        if response.status_code >= 400:
            raise OpenCodeError(f"OpenCode rejected {method} {path} with HTTP {response.status_code}")
        return response


def _session(data: dict[str, Any]) -> Session:
    return Session(
        id=str(data["id"]),
        directory=str(data.get("directory", "")),
        title=str(data.get("title", "")),
        time=data.get("time") if isinstance(data.get("time"), dict) else None,
        parent_id=_optional_string(data.get("parentID")),
    )


def _todo(data: dict[str, Any]) -> Todo:
    return Todo(content=str(data.get("content", "")), status=str(data.get("status", "")))


def _message(data: dict[str, Any]) -> Message:
    info = data.get("info") if isinstance(data.get("info"), dict) else data
    raw_parts = data.get("parts", ())
    parts = tuple(part for part in raw_parts if isinstance(part, dict)) if isinstance(raw_parts, list) else ()
    return Message(
        id=str(info.get("id", data.get("id", ""))),
        role=str(info.get("role", data.get("role", ""))),
        time=info.get("time") if isinstance(info.get("time"), dict) else None,
        parts=parts,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
