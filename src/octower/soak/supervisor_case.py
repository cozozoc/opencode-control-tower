"""Real BackendProcess composition for deterministic Case H verification."""

from __future__ import annotations

from pathlib import Path

import anyio

from octower.models import AgentState
from octower.supervisor.backend import (
    BackendConfig,
    BackendDependencies,
    BackendProcess,
)
from octower.supervisor.launcher import LaunchIdentity, LaunchPlan
from octower.supervisor.rehydration import (
    RehydratedSession,
    RootRestoreState,
)


class _Process:
    def __init__(self) -> None:
        self._running = True

    @property
    def running(self) -> bool:
        return self._running

    async def terminate(self) -> None:
        self._running = False

    async def wait(self) -> None:
        return None

    async def kill(self) -> None:
        self._running = False


class _Runner:
    def __init__(self) -> None:
        self.starts = 0

    async def start(self, command: tuple[str, ...], cwd: Path) -> _Process:
        del command, cwd
        self.starts += 1
        return _Process()


class _Health:
    def __init__(self) -> None:
        self._results = [False, False, False, True]

    async def healthy(self, endpoint: str) -> bool:
        del endpoint
        return self._results.pop(0)


class _Rehydration:
    def __init__(self) -> None:
        self.resumed: list[str] = []

    async def reenumerate_sessions(self) -> tuple[str, ...]:
        return ("root", "active", "recovering", "done", "failed", "historical")

    async def restore_root(
        self, root_id: str, sessions: tuple[str, ...]
    ) -> RootRestoreState:
        del root_id, sessions
        return RootRestoreState.READY

    async def reload_journal(self) -> tuple[str, ...]:
        return ("recovering",)

    async def reclassify(
        self, sessions: tuple[str, ...], recovering_sessions: tuple[str, ...]
    ) -> tuple[RehydratedSession, ...]:
        del sessions, recovering_sessions
        return (
            RehydratedSession("active", AgentState.RUNNING, AgentState.RUNNING, True),
            RehydratedSession(
                "recovering", AgentState.RECOVERING, AgentState.RECOVERING, True
            ),
            RehydratedSession("done", AgentState.DONE, AgentState.DONE, False),
            RehydratedSession(
                "failed", AgentState.FAILED_RECOVERY, AgentState.FAILED_RECOVERY, True
            ),
            RehydratedSession(
                "historical", AgentState.DISCOVERED, AgentState.WAITING, True
            ),
        )

    async def resume(self, session_id: str) -> None:
        self.resumed.append(session_id)


class _Tui:
    async def reattach(self, root_id: str) -> bool:
        del root_id
        return True


async def _run_case() -> tuple[int, tuple[str, ...]]:
    runner = _Runner()
    rehydration = _Rehydration()
    plan = LaunchPlan(
        Path("."),
        LaunchIdentity(43121, "soak-case-h"),
        "http://127.0.0.1:43121",
        ("mock-opencode", "serve"),
        None,
    )
    backend = BackendProcess(
        BackendConfig(
            plan,
            "root",
            health_timeout=1,
            restart_timeout=1,
            poll_seconds=0,
        ),
        BackendDependencies(runner, _Health(), rehydration, _Tui()),
    )
    await backend.start()
    await backend.monitor_once()
    await backend.monitor_once()
    await backend.monitor_once()
    await backend.shutdown()
    return backend.report.restarts, tuple(rehydration.resumed)


def run_backend_restart_case() -> tuple[int, tuple[str, ...]]:
    """Run three failed health probes and the real rehydration path without sleeping."""
    return anyio.run(_run_case)
