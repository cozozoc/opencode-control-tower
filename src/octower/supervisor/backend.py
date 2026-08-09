"""AnyIO backend process supervision and exact R11 restart rehydration (§15, Case H)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol, assert_never

import anyio

from octower.supervisor.launcher import LaunchPlan
from octower.supervisor.process import (
    ProcessHandle,
    ProcessRunner,
    ProcessStartError,
    stop_process,
)
from octower.supervisor.rehydration import (
    RehydratedSession,
    RehydrationActions,
    RootRestoreState,
    eligible_for_resume,
)


class BackendState(str, Enum):
    """Operational state exposed by the process supervisor."""

    STARTING = "starting"
    HEALTHY = "healthy"
    DOWN = "down"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


class HealthProbe(Protocol):
    """Injected ``GET /global/health`` probe for the configured endpoint."""

    async def healthy(self, endpoint: str) -> bool: ...


class TuiController(Protocol):
    """Independent attach lifecycle notified only after a healthy restart."""

    async def reattach(self, root_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class BackendConfig:
    """Timing and safety policy for one fixed localhost launch plan."""

    plan: LaunchPlan
    root_session_id: str
    failure_threshold: int = 3
    max_restarts: int = 2
    health_timeout: float = 2.0
    restart_timeout: float = 30.0
    poll_seconds: float = 5.0
    shutdown_timeout: float = 5.0


@dataclass(frozen=True, slots=True)
class BackendDependencies:
    """All process, health, rehydration, and TUI side effects."""

    runner: ProcessRunner
    health: HealthProbe
    rehydration: RehydrationActions
    tui: TuiController


@dataclass(frozen=True, slots=True)
class BackendReport:
    """Current observable supervisor result for the future control tower UI."""

    state: BackendState = BackendState.STARTING
    consecutive_failures: int = 0
    restarts: int = 0
    reason: str = "backend has not started"


class BackendProcess:
    """Mutable process state machine that owns exactly one backend child (§15)."""

    def __init__(self, config: BackendConfig, dependencies: BackendDependencies) -> None:
        self._config = config
        self._dependencies = dependencies
        self._process: ProcessHandle | None = None
        self._stop_requested = anyio.Event()
        self.report = BackendReport()

    @property
    def endpoint(self) -> str:
        return self._config.plan.endpoint

    async def start(self) -> None:
        """Start the backend once through the injected process boundary."""
        self._process = await self._dependencies.runner.start(
            self._config.plan.backend_command, self._config.plan.project
        )
        self.report = BackendReport(BackendState.STARTING, reason="backend process started")

    async def run(self) -> None:
        """Monitor under structured concurrency until ``request_stop`` is called."""
        await self.start()
        try:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(self._monitor_loop)
                await self._stop_requested.wait()
                task_group.cancel_scope.cancel()
        finally:
            await self.shutdown()

    def request_stop(self) -> None:
        """Request orderly loop cancellation without bypassing child cleanup."""
        self._stop_requested.set()

    async def monitor_once(self) -> None:
        """Apply Case H's three-consecutive-failure trigger for one health sample."""
        if self.report.state in {BackendState.FAILED, BackendState.STOPPED}:
            return
        if await self._probe_health():
            self.report = replace(
                self.report,
                state=BackendState.HEALTHY,
                consecutive_failures=0,
                reason="backend health check passed",
            )
            return
        failures = self.report.consecutive_failures + 1
        self.report = replace(
            self.report,
            state=BackendState.DOWN,
            consecutive_failures=failures,
            reason="backend health check failed",
        )
        if failures >= self._config.failure_threshold:
            await self._restart()

    async def shutdown(self) -> None:
        """Terminate, wait, and force-kill only when graceful shutdown times out."""
        await self._stop_child()
        self.report = replace(self.report, state=BackendState.STOPPED, reason="backend stopped")

    async def _monitor_loop(self) -> None:
        while True:
            await self.monitor_once()
            if self.report.state is BackendState.FAILED:
                self.request_stop()
                return
            await anyio.sleep(self._config.poll_seconds)

    async def _probe_health(self) -> bool:
        healthy = False
        with anyio.move_on_after(self._config.health_timeout) as scope:
            healthy = await self._dependencies.health.healthy(self.endpoint)
        return healthy and not scope.cancelled_caught

    async def _restart(self) -> None:
        if self.report.restarts >= self._config.max_restarts:
            self.report = replace(
                self.report, state=BackendState.FAILED, reason="backend restart cap reached"
            )
            return
        await self._stop_child()
        try:
            self._process = await self._dependencies.runner.start(
                self._config.plan.backend_command, self._config.plan.project
            )
        except ProcessStartError:
            self.report = replace(
                self.report, state=BackendState.FAILED, reason="backend restart process failed"
            )
            return
        self.report = replace(
            self.report,
            restarts=self.report.restarts + 1,
            consecutive_failures=0,
            reason="backend restarted; awaiting health",
        )
        healthy = False
        with anyio.move_on_after(self._config.restart_timeout) as scope:
            while not healthy:
                healthy = await self._probe_health()
                if not healthy:
                    await anyio.sleep(self._config.poll_seconds)
        if scope.cancelled_caught or not healthy:
            await self._stop_child()
            self.report = replace(
                self.report, state=BackendState.FAILED, reason="backend restart health timeout"
            )
            return
        await self._rehydrate()

    async def _rehydrate(self) -> None:
        actions = self._dependencies.rehydration
        sessions = await actions.reenumerate_sessions()
        root_state = await actions.restore_root(self._config.root_session_id, sessions)
        recovering_sessions = await actions.reload_journal()
        match root_state:
            case RootRestoreState.READY:
                pass
            case RootRestoreState.MISSING | RootRestoreState.DEGRADED:
                self.report = replace(
                    self.report, state=BackendState.DEGRADED,
                    reason=f"root restoration {root_state.value}",
                )
                return
            case unreachable:
                assert_never(unreachable)
        classified = await actions.reclassify(sessions, recovering_sessions)
        for session in classified:
            if eligible_for_resume(session):
                await actions.resume(session.session_id)
        await self._dependencies.tui.reattach(self._config.root_session_id)
        self.report = replace(
            self.report, state=BackendState.HEALTHY, reason="backend restart rehydration completed"
        )

    async def _stop_child(self) -> None:
        process = self._process
        self._process = None
        if process is not None:
            await stop_process(process, self._config.shutdown_timeout)
