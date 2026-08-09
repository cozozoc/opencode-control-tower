from __future__ import annotations

from pathlib import Path

import pytest

from octower.supervisor.launcher import (
    LOCALHOST,
    HostPlatform,
    LaunchIdentity,
    LauncherConfig,
    LaunchMode,
    LocalhostBindingError,
    TmuxPlatformError,
    allocate_identity,
    build_launch_plan,
    resolve_opencode_executable,
)


def test_split_mode_builds_serve_and_root_attach_commands() -> None:
    config = LauncherConfig(Path("C:/work/project"), "ses-root")

    plan = build_launch_plan(config, LaunchIdentity(43121, "octower-a1"), "opencode.exe")

    assert plan.backend_command == (
        "opencode.exe", "serve", "--port", "43121", "--hostname", LOCALHOST,
    )
    assert plan.attach_command == (
        "opencode.exe", "attach", "http://127.0.0.1:43121", "--session", "ses-root",
    )


def test_integrated_mode_builds_one_process_without_attach() -> None:
    config = LauncherConfig(Path("C:/work/project"), "ses-root", mode=LaunchMode.INTEGRATED)

    plan = build_launch_plan(config, LaunchIdentity(43122, "octower-a2"), "opencode.exe")

    assert plan.backend_command == (
        "opencode.exe", "--port", "43122", "--hostname", LOCALHOST,
    )
    assert plan.attach_command is None


def test_launcher_rejects_non_localhost_binding() -> None:
    config = LauncherConfig(Path("C:/work/project"), "ses-root", hostname="0.0.0.0")

    with pytest.raises(LocalhostBindingError):
        build_launch_plan(config, LaunchIdentity(43123, "octower-a3"), "opencode.exe")


def test_identity_allocation_uses_unique_port_and_workspace_name() -> None:
    ports = iter((43124, 43125))
    tokens = iter(("first", "second"))

    first = allocate_identity(lambda: next(ports), lambda: next(tokens))
    second = allocate_identity(lambda: next(ports), lambda: next(tokens))

    assert first != second
    assert first.workspace_name == "octower-first"
    assert second.workspace_name == "octower-second"


def test_windows_resolution_prefers_verified_npm_global_executable() -> None:
    expected = Path(
        "C:/Users/thomas/AppData/Roaming/npm/node_modules/opencode-ai/bin/opencode.exe"
    )

    resolved = resolve_opencode_executable(
        HostPlatform.WINDOWS,
        path_exists=lambda path: path == expected,
        which=lambda _name: "C:/fallback/opencode.exe",
    )

    assert resolved == str(expected)


def test_windows_resolution_falls_back_to_path_lookup() -> None:
    resolved = resolve_opencode_executable(
        HostPlatform.WINDOWS,
        path_exists=lambda _path: False,
        which=lambda _name: "C:/fallback/opencode.exe",
    )

    assert resolved == "C:/fallback/opencode.exe"


def test_wsl_tmux_uses_unique_name_without_kill_or_fixed_workspace_reuse() -> None:
    config = LauncherConfig(
        Path("/work/project"),
        "ses-root",
        platform=HostPlatform.WSL2,
        use_tmux=True,
    )

    plan = build_launch_plan(config, LaunchIdentity(43126, "octower-unique"), "opencode")

    assert plan.backend_command[:6] == (
        "tmux", "new-session", "-d", "-s", "octower-unique", "-n",
    )
    assert plan.attach_command is not None
    assert "new-window" in plan.attach_command
    assert "kill-session" not in plan.backend_command + plan.attach_command


def test_tmux_requires_explicit_wsl2_platform() -> None:
    config = LauncherConfig(
        Path("C:/work/project"),
        "ses-root",
        platform=HostPlatform.WINDOWS,
        use_tmux=True,
    )

    with pytest.raises(TmuxPlatformError):
        build_launch_plan(config, LaunchIdentity(43127, "octower-a4"), "opencode.exe")
