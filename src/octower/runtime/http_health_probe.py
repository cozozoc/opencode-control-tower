"""HTTP health boundary for a real localhost OpenCode server (§15)."""

from __future__ import annotations

import httpx


class HttpHealthProbe:
    """Probe OpenCode health with an injectable asynchronous HTTP client."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        timeout: float = 2.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._timeout = timeout

    async def healthy(self, endpoint: str) -> bool:
        try:
            response = await self._client.get(
                f"{endpoint.rstrip('/')}/global/health", timeout=self._timeout
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def aclose(self) -> None:
        """Close only the client created by this probe."""
        if self._owns_client:
            await self._client.aclose()
