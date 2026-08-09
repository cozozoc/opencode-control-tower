"""Real subprocess boundary for the backend supervisor (§15)."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import subprocess
import sys

import anyio

from octower.supervisor.process import ProcessStartError
from octower.supervisor.process import stop_process as _stop_process


def _on_windows() -> bool:
    return sys.platform == "win32"


class SubprocessHandle:
    """AnyIO-safe wrapper around one operating-system child process."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self._process = process

    @property
    def running(self) -> bool:
        return self._process.poll() is None

    async def terminate(self) -> None:
        await anyio.to_thread.run_sync(self._process.terminate)

    async def wait(self) -> None:
        await anyio.to_thread.run_sync(self._process.wait)

    async def kill(self) -> None:
        await anyio.to_thread.run_sync(self._process.kill)


class SubprocessRunner:
    """Spawn isolated OpenCode children without blocking the AnyIO loop."""

    def __init__(self, env: Mapping[str, str]) -> None:
        self._env = dict(env)

    async def start(self, command: tuple[str, ...], cwd: Path) -> SubprocessHandle:
        try:
            process = await anyio.to_thread.run_sync(self._spawn, command, cwd)
        except OSError as error:
            raise ProcessStartError(command) from error
        return SubprocessHandle(process)

    def _spawn(self, command: tuple[str, ...], cwd: Path) -> subprocess.Popen[bytes]:
        kwargs: dict = {
            "cwd": str(cwd),
            "env": self._env,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if _on_windows():
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["preexec_fn"] = os.setsid
        return subprocess.Popen(command, **kwargs)


async def stop_process(handle: SubprocessHandle, timeout: float) -> None:
    """Apply the supervisor's bounded terminate/wait/kill cleanup contract."""
    await _stop_process(handle, timeout)
