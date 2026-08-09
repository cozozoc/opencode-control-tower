"""Independent OpenCode root-session attach supervision (§15, R11 step 9)."""

from __future__ import annotations

from dataclasses import dataclass

import anyio

from octower.supervisor.process import (
    ProcessHandle,
    ProcessRunner,
    ProcessStartError,
    stop_process,
)
from octower.supervisor.launcher import LaunchPlan


@dataclass(frozen=True, slots=True)
class TuiConfig:
    """Bounded retry and cleanup timing for the attach client."""

    max_attempts: int = 3
    backoff_seconds: float = 0.25
    max_backoff_seconds: float = 5.0
    shutdown_timeout: float = 5.0


class TuiAttach:
    """Mutable attach owner whose failures never drive backend restart decisions."""

    def __init__(self, plan: LaunchPlan, runner: ProcessRunner, config: TuiConfig | None = None) -> None:
        self._plan = plan
        self._runner = runner
        self._config = config or TuiConfig()
        self._process: ProcessHandle | None = None

    async def ensure_running(self, root_id: str) -> bool:
        """Start or retry the attach process while leaving backend ownership untouched."""
        if self._plan.attach_command is None:
            return True
        if self._process is not None and self._process.running:
            return True
        command = _root_attach_command(self._plan.attach_command, root_id)
        delay = self._config.backoff_seconds
        for attempt in range(self._config.max_attempts):
            try:
                self._process = await self._runner.start(command, self._plan.project)
            except ProcessStartError:
                if attempt + 1 < self._config.max_attempts:
                    await anyio.sleep(delay)
                    delay = min(delay * 2, self._config.max_backoff_seconds)
            else:
                return True
        return False

    async def reattach(self, root_id: str) -> bool:
        """Respawn attach after a healthy backend restart (R11 step 9)."""
        await self.shutdown()
        return await self.ensure_running(root_id)

    async def shutdown(self) -> None:
        """Stop only the attach child, never the independently monitored backend."""
        process = self._process
        self._process = None
        if process is not None:
            await stop_process(process, self._config.shutdown_timeout)


def _root_attach_command(command: tuple[str, ...], root_id: str) -> tuple[str, ...]:
    session_index = command.index("--session") + 1
    return command[:session_index] + (root_id,) + command[session_index + 1 :]
