from __future__ import annotations

from pathlib import Path

import anyio

from octower.supervisor.backend import ProcessStartError
from octower.supervisor.launcher import LaunchIdentity, LauncherConfig, build_launch_plan
from octower.supervisor.tui import TuiAttach, TuiConfig


class FakeProcess:
    def __init__(self) -> None:
        self.running = True
        self.terminated = False
        self.killed = False

    async def terminate(self) -> None:
        self.terminated = True
        self.running = False

    async def wait(self) -> None:
        return

    async def kill(self) -> None:
        self.killed = True
        self.running = False


class FakeRunner:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.commands: list[tuple[str, ...]] = []
        self.processes: list[FakeProcess] = []

    async def start(self, command: tuple[str, ...], cwd: Path) -> FakeProcess:
        self.commands.append(command)
        if self.failures > 0:
            self.failures -= 1
            raise ProcessStartError(command)
        process = FakeProcess()
        self.processes.append(process)
        return process


def _plan():
    return build_launch_plan(
        LauncherConfig(Path("C:/work/project"), "ses-root"),
        LaunchIdentity(43201, "octower-tui"),
        "opencode.exe",
    )


def test_backend_restart_respawns_attach_without_restarting_backend() -> None:
    runner = FakeRunner()
    tui = TuiAttach(_plan(), runner, TuiConfig(backoff_seconds=0))

    async def scenario() -> None:
        assert await tui.ensure_running("ses-root") is True
        first = runner.processes[0]
        assert await tui.reattach("ses-root") is True
        assert first.terminated is True

    anyio.run(scenario)

    assert len(runner.commands) == 2
    assert all(command[1] == "attach" for command in runner.commands)


def test_attach_retries_with_bounded_backoff() -> None:
    runner = FakeRunner(failures=2)
    tui = TuiAttach(_plan(), runner, TuiConfig(max_attempts=3, backoff_seconds=0))

    result = anyio.run(tui.ensure_running, "ses-root")

    assert result is True
    assert len(runner.commands) == 3


def test_attach_failure_is_reported_without_backend_side_effect() -> None:
    runner = FakeRunner(failures=3)
    tui = TuiAttach(_plan(), runner, TuiConfig(max_attempts=2, backoff_seconds=0))

    result = anyio.run(tui.ensure_running, "ses-root")

    assert result is False
    assert len(runner.commands) == 2


def test_healthy_existing_attach_is_independent_of_backend_health_polling() -> None:
    runner = FakeRunner()
    tui = TuiAttach(_plan(), runner, TuiConfig(backoff_seconds=0))

    async def scenario() -> None:
        assert await tui.ensure_running("ses-root") is True
        assert await tui.ensure_running("ses-root") is True

    anyio.run(scenario)

    assert len(runner.commands) == 1
