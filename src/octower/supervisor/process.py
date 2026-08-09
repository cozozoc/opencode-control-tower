"""Injected child-process contracts and bounded cleanup for Phase 5 (§15)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anyio


@dataclass(frozen=True, slots=True)
class ProcessStartError(RuntimeError):
    """An injected runner could not create the requested child process."""

    command: tuple[str, ...]

    def __str__(self) -> str:
        return f"failed to start process: {self.command[0]}"


class ProcessHandle(Protocol):
    """Minimal child-process lifecycle needed for orphan-free shutdown."""

    @property
    def running(self) -> bool: ...

    async def terminate(self) -> None: ...

    async def wait(self) -> None: ...

    async def kill(self) -> None: ...


class ProcessRunner(Protocol):
    """Injected process boundary; tests never spawn operating-system processes."""

    async def start(self, command: tuple[str, ...], cwd: Path) -> ProcessHandle: ...


async def stop_process(process: ProcessHandle, timeout: float) -> None:
    """Use terminate/wait with a bounded force-kill fallback to prevent orphans."""
    await process.terminate()
    with anyio.move_on_after(timeout, shield=True) as scope:
        await process.wait()
    if scope.cancelled_caught:
        await process.kill()
        with anyio.move_on_after(timeout, shield=True):
            await process.wait()
