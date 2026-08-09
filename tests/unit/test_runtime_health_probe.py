from __future__ import annotations

import anyio
import httpx


def test_health_probe_reports_only_successful_health_response() -> None:
    from octower.runtime.http_health_probe import HttpHealthProbe

    statuses = iter((200, 503))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/global/health"
        return httpx.Response(next(statuses), request=request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            probe = HttpHealthProbe(client=client)
            assert await probe.healthy("http://127.0.0.1:43123") is True
            assert await probe.healthy("http://127.0.0.1:43123") is False

    anyio.run(scenario)


def test_health_probe_converts_transport_failure_to_unhealthy() -> None:
    from octower.runtime.http_health_probe import HttpHealthProbe

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("server unavailable", request=request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            probe = HttpHealthProbe(client=client)
            assert await probe.healthy("http://127.0.0.1:43123") is False

    anyio.run(scenario)
