from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import subprocess

import anyio
import pytest


class FakePopen:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False
        self.waited = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def wait(self) -> int:
        self.waited = True
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = 1


def test_runner_starts_isolated_windows_process_and_controls_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octower.runtime.subprocess_runner import SubprocessRunner

    captured: dict[str, str | int | tuple[str, ...] | Mapping[str, str]] = {}
    process = FakePopen()

    def fake_popen(
        command: tuple[str, ...],
        *,
        cwd: str,
        env: Mapping[str, str],
        stdout: int,
        stderr: int,
        creationflags: int,
    ) -> FakePopen:
        captured.update(
            command=command,
            cwd=cwd,
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    runner = SubprocessRunner(env={"XDG_DATA_HOME": "C:/isolated"})

    async def scenario() -> None:
        handle = await runner.start(("opencode.exe", "serve"), Path("C:/project"))
        assert handle.running is True
        await handle.terminate()
        await handle.wait()
        await handle.kill()

    anyio.run(scenario)

    assert captured["command"] == ("opencode.exe", "serve")
    assert captured["cwd"] == "C:\\project"
    assert captured["env"] == {"XDG_DATA_HOME": "C:/isolated"}
    assert captured["stdout"] == subprocess.DEVNULL
    assert captured["stderr"] == subprocess.DEVNULL
    assert captured["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
    assert process.terminated is True
    assert process.waited is True
    assert process.killed is True
