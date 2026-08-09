"""Safe native-Windows and optional WSL2/tmux launch construction (§15, §22-§23)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import shutil
import socket
from typing import Final, assert_never
from uuid import uuid4


LOCALHOST: Final = "127.0.0.1"
WINDOWS_NPM_EXECUTABLE: Final = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "npm"
    / "node_modules"
    / "opencode-ai"
    / "bin"
    / "opencode.exe"
)


class LaunchMode(str, Enum):
    """Verified split default and integrated compatibility fallback (§15)."""

    SPLIT = "split"
    INTEGRATED = "integrated"


class HostPlatform(str, Enum):
    """Supported process containment environments from the compatibility report."""

    WINDOWS = "windows"
    WSL2 = "wsl2"


@dataclass(frozen=True, slots=True)
class LocalhostBindingError(ValueError):
    """A launch attempted to expose the local control API beyond R12."""

    hostname: str

    def __str__(self) -> str:
        return f"control API hostname must be {LOCALHOST}, got {self.hostname}"


@dataclass(frozen=True, slots=True)
class TmuxPlatformError(ValueError):
    """tmux was requested outside the explicitly selected WSL2 runtime."""

    platform: HostPlatform

    def __str__(self) -> str:
        return f"tmux launch requires WSL2, got {self.platform.value}"


@dataclass(frozen=True, slots=True)
class ExecutableNotFoundError(RuntimeError):
    """No verified or PATH-resolved OpenCode executable exists."""

    executable: str

    def __str__(self) -> str:
        return f"OpenCode executable was not found: {self.executable}"


@dataclass(frozen=True, slots=True)
class LaunchIdentity:
    """Collision-resistant localhost port and workspace allocation (§23)."""

    port: int
    workspace_name: str


@dataclass(frozen=True, slots=True)
class LauncherConfig:
    """Inputs that determine one backend/TUI process topology."""

    project: Path
    root_session_id: str
    mode: LaunchMode = LaunchMode.SPLIT
    hostname: str = LOCALHOST
    platform: HostPlatform = HostPlatform.WINDOWS
    use_tmux: bool = False


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    """Side-effect-free commands consumed by injected process runners."""

    project: Path
    identity: LaunchIdentity
    endpoint: str
    backend_command: tuple[str, ...]
    attach_command: tuple[str, ...] | None


def allocate_identity(
    port_allocator: Callable[[], int] = lambda: allocate_localhost_port(),
    token_factory: Callable[[], str] = lambda: uuid4().hex,
) -> LaunchIdentity:
    """Allocate a fresh endpoint and name instead of reusing fixed process state."""
    return LaunchIdentity(port_allocator(), f"octower-{token_factory()}")


def allocate_localhost_port() -> int:
    """Ask the OS for an available localhost port without starting OpenCode."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((LOCALHOST, 0))
        port = listener.getsockname()[1]
    return int(port)


def resolve_opencode_executable(
    platform: HostPlatform,
    *,
    path_exists: Callable[[Path], bool] = Path.exists,
    which: Callable[[str], str | None] = shutil.which,
) -> str:
    """Prefer the verified Windows npm executable, then use PATH resolution."""
    match platform:
        case HostPlatform.WINDOWS:
            if path_exists(WINDOWS_NPM_EXECUTABLE):
                return str(WINDOWS_NPM_EXECUTABLE)
            name = "opencode.exe"
        case HostPlatform.WSL2:
            name = "opencode"
        case unreachable:
            assert_never(unreachable)
    resolved = which(name)
    if resolved is None:
        raise ExecutableNotFoundError(name)
    return resolved


def build_launch_plan(
    config: LauncherConfig, identity: LaunchIdentity, executable: str
) -> LaunchPlan:
    """Construct split/integrated and guarded tmux commands without launching them."""
    if config.hostname != LOCALHOST:
        raise LocalhostBindingError(config.hostname)
    if config.use_tmux and config.platform is not HostPlatform.WSL2:
        raise TmuxPlatformError(config.platform)

    endpoint = f"http://{LOCALHOST}:{identity.port}"
    match config.mode:
        case LaunchMode.SPLIT:
            backend = (
                executable, "serve", "--port", str(identity.port), "--hostname", LOCALHOST,
            )
            attach = (
                executable, "attach", endpoint, "--session", config.root_session_id,
            )
        case LaunchMode.INTEGRATED:
            backend = (
                executable, "--port", str(identity.port), "--hostname", LOCALHOST,
            )
            attach = None
        case unreachable:
            assert_never(unreachable)

    if config.use_tmux:
        backend = (
            "tmux", "new-session", "-d", "-s", identity.workspace_name,
            "-n", "backend", *backend,
        )
        if attach is not None:
            attach = (
                "tmux", "new-window", "-t", identity.workspace_name,
                "-n", "opencode", *attach,
            )
    return LaunchPlan(config.project, identity, endpoint, backend, attach)
