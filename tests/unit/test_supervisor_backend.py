from __future__ import annotations

from pathlib import Path

import anyio
import pytest

from octower.models import AgentState
from octower.supervisor.backend import (
    BackendConfig,
    BackendDependencies,
    BackendProcess,
    BackendState,
    RehydratedSession,
    RootRestoreState,
)
from octower.supervisor.launcher import LaunchIdentity, LauncherConfig, build_launch_plan


class FakeProcess:
    def __init__(self, wait_blocks: bool = False) -> None:
        self.running = True
        self.wait_blocks = wait_blocks
        self.terminated = False
        self.killed = False

    async def terminate(self) -> None:
        self.terminated = True
        if not self.wait_blocks:
            self.running = False

    async def wait(self) -> None:
        while self.running:
            await anyio.sleep(0)

    async def kill(self) -> None:
        self.killed = True
        self.running = False


class FakeRunner:
    def __init__(self, wait_blocks: bool = False) -> None:
        self.wait_blocks = wait_blocks
        self.starts: list[tuple[tuple[str, ...], Path]] = []
        self.processes: list[FakeProcess] = []

    async def start(self, command: tuple[str, ...], cwd: Path) -> FakeProcess:
        self.starts.append((command, cwd))
        process = FakeProcess(self.wait_blocks)
        self.processes.append(process)
        return process


class FakeHealth:
    def __init__(self, results: list[bool]) -> None:
        self.results = results
        self.endpoints: list[str] = []

    async def healthy(self, endpoint: str) -> bool:
        self.endpoints.append(endpoint)
        return self.results.pop(0) if self.results else False


class FakeRehydration:
    def __init__(self) -> None:
        self.root_state = RootRestoreState.READY
        self.sessions = ("root", "active", "recovering", "done", "failed", "historical")
        self.journal_sessions = ("recovering",)
        self.classified = (
            RehydratedSession("active", AgentState.RUNNING, AgentState.RUNNING, True),
            RehydratedSession("recovering", AgentState.RECOVERING, AgentState.RECOVERING, True),
            RehydratedSession("done", AgentState.DONE, AgentState.DONE, False),
            RehydratedSession("failed", AgentState.FAILED_RECOVERY, AgentState.FAILED_RECOVERY, True),
            RehydratedSession("historical", AgentState.DISCOVERED, AgentState.WAITING, True),
        )
        self.calls: list[str] = []
        self.resumed: list[str] = []

    async def reenumerate_sessions(self) -> tuple[str, ...]:
        self.calls.append("enumerate")
        return self.sessions

    async def restore_root(self, root_id: str, sessions: tuple[str, ...]) -> RootRestoreState:
        self.calls.append("restore-root")
        return self.root_state

    async def reload_journal(self) -> tuple[str, ...]:
        self.calls.append("reload-journal")
        return self.journal_sessions

    async def reclassify(
        self, sessions: tuple[str, ...], recovering_sessions: tuple[str, ...]
    ) -> tuple[RehydratedSession, ...]:
        self.calls.append("reclassify")
        return self.classified

    async def resume(self, session_id: str) -> None:
        self.calls.append(f"resume:{session_id}")
        self.resumed.append(session_id)


class FakeTui:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.roots: list[str] = []

    async def reattach(self, root_id: str) -> bool:
        self.roots.append(root_id)
        return self.result


def _supervisor(
    health: FakeHealth,
    *,
    max_restarts: int = 2,
    restart_timeout: float = 0.02,
    wait_blocks: bool = False,
):
    plan = build_launch_plan(
        LauncherConfig(Path("C:/work/project"), "root"),
        LaunchIdentity(43301, "octower-backend"),
        "opencode.exe",
    )
    runner = FakeRunner(wait_blocks)
    rehydration = FakeRehydration()
    tui = FakeTui()
    config = BackendConfig(
        plan=plan,
        root_session_id="root",
        failure_threshold=3,
        max_restarts=max_restarts,
        health_timeout=0.01,
        restart_timeout=restart_timeout,
        poll_seconds=0,
        shutdown_timeout=0.001,
    )
    dependencies = BackendDependencies(runner, health, rehydration, tui)
    return BackendProcess(config, dependencies), runner, rehydration, tui


def test_three_consecutive_health_failures_restart_same_local_endpoint() -> None:
    supervisor, runner, _, _ = _supervisor(FakeHealth([False, False, False, True]))

    async def scenario() -> None:
        await supervisor.start()
        await supervisor.monitor_once()
        await supervisor.monitor_once()
        await supervisor.monitor_once()

    anyio.run(scenario)

    assert supervisor.report.restarts == 1
    assert len(runner.starts) == 2
    assert runner.starts[0][0] == runner.starts[1][0]
    assert supervisor.endpoint == "http://127.0.0.1:43301"


def test_health_success_resets_consecutive_failure_counter() -> None:
    supervisor, _, _, _ = _supervisor(FakeHealth([False, False, True, False]))

    async def scenario() -> None:
        await supervisor.start()
        for _ in range(4):
            await supervisor.monitor_once()

    anyio.run(scenario)

    assert supervisor.report.consecutive_failures == 1
    assert supervisor.report.restarts == 0


def test_restart_rehydrates_in_r11_order_and_resumes_only_unfinished_active_work() -> None:
    supervisor, _, rehydration, tui = _supervisor(FakeHealth([False, False, False, True]))
    tui.result = False

    async def scenario() -> None:
        await supervisor.start()
        for _ in range(3):
            await supervisor.monitor_once()

    anyio.run(scenario)

    assert rehydration.calls == [
        "enumerate", "restore-root", "reload-journal", "reclassify",
        "resume:active", "resume:recovering",
    ]
    assert rehydration.resumed == ["active", "recovering"]
    assert tui.roots == ["root"]
    assert supervisor.report.state is BackendState.HEALTHY


@pytest.mark.parametrize("root_state", [RootRestoreState.MISSING, RootRestoreState.DEGRADED])
def test_missing_or_degraded_root_fails_safe(root_state: RootRestoreState) -> None:
    supervisor, _, rehydration, tui = _supervisor(FakeHealth([False, False, False, True]))
    rehydration.root_state = root_state

    async def scenario() -> None:
        await supervisor.start()
        for _ in range(3):
            await supervisor.monitor_once()

    anyio.run(scenario)

    assert supervisor.report.state is BackendState.DEGRADED
    assert rehydration.resumed == []
    assert tui.roots == []
    assert "reload-journal" in rehydration.calls


def test_restart_cap_transitions_to_failed_without_spawning_again() -> None:
    health = FakeHealth([False, False, False, True, False, False, False])
    supervisor, runner, _, _ = _supervisor(health, max_restarts=1)

    async def scenario() -> None:
        await supervisor.start()
        for _ in range(6):
            await supervisor.monitor_once()

    anyio.run(scenario)

    assert supervisor.report.state is BackendState.FAILED
    assert len(runner.starts) == 2


def test_restart_health_timeout_fails_and_cleans_replacement_process() -> None:
    supervisor, runner, _, _ = _supervisor(FakeHealth([False, False, False]), restart_timeout=0.001)

    async def scenario() -> None:
        await supervisor.start()
        for _ in range(3):
            await supervisor.monitor_once()

    anyio.run(scenario)

    assert supervisor.report.state is BackendState.FAILED
    assert runner.processes[-1].terminated is True


def test_graceful_shutdown_force_kills_child_when_wait_times_out() -> None:
    supervisor, runner, _, _ = _supervisor(FakeHealth([]), wait_blocks=True)

    async def scenario() -> None:
        await supervisor.start()
        await supervisor.shutdown()

    anyio.run(scenario)

    assert runner.processes[0].terminated is True
    assert runner.processes[0].killed is True
    assert supervisor.report.state is BackendState.STOPPED
