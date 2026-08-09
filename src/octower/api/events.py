"""Reconnect-capable asynchronous OpenCode ``/event`` SSE subscription (§8, §17)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
import json
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class OpenCodeEvent:
    """A typed OpenCode event whose payload remains available for version compatibility."""

    type: str
    properties: dict[str, Any]
    raw: dict[str, Any]

    @property
    def session_id(self) -> str | None:
        """Extract the conventional session identifier from known event payload shapes."""
        for data in (self.properties, self.raw):
            for key in ("sessionID", "sessionId", "id"):
                value = data.get(key)
                if isinstance(value, str):
                    return value
            info = data.get("info")
            if isinstance(info, dict):
                for key in ("sessionID", "id"):
                    if isinstance(info.get(key), str):
                        return info[key]
        return None


def parse_sse_data(line: str) -> OpenCodeEvent | None:
    """Parse one ``data: {json}`` SSE line, ignoring comments and blank delimiters."""
    if not line.startswith("data:"):
        return None
    try:
        data = json.loads(line[5:].lstrip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("type"), str):
        return None
    properties = data.get("properties")
    return OpenCodeEvent(data["type"], properties if isinstance(properties, dict) else {}, data)


async def parse_sse_lines(lines: AsyncIterable[str]) -> AsyncIterator[OpenCodeEvent]:
    """Yield typed events from a line stream; SSE records are data-only in 1.18.15."""
    async for line in lines:
        event = parse_sse_data(line)
        if event is not None:
            yield event


class OpenCodeEventStream:
    """Async SSE subscriber with bounded exponential reconnect delay (§17)."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float | httpx.Timeout | None = None,
        initial_backoff: float = 0.25,
        max_backoff: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(transport=transport, timeout=timeout)
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff

    async def aclose(self) -> None:
        """Close an internally-created asynchronous HTTP client."""
        if self._owns_client:
            await self._client.aclose()

    async def events(self) -> AsyncIterator[OpenCodeEvent]:
        """Yield events forever, reconnecting after recoverable stream failures (§17)."""
        delay = self._initial_backoff
        while True:
            try:
                async with self._client.stream("GET", f"{self.base_url}/event") as response:
                    response.raise_for_status()
                    received = False
                    async for event in parse_sse_lines(response.aiter_lines()):
                        received = True
                        delay = self._initial_backoff
                        yield event
                    if received:
                        continue
            except asyncio.CancelledError:
                raise
            except httpx.HTTPError:
                pass
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._max_backoff)
