"""Real ``octower start`` runtime composition for OpenCode (짠15)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import tempfile
import time
from types import FrameType
from typing import Final
from uuid import uuid4

import anyio

from octower.api.opencode import OpenCodeClient
from octower.discovery.reconciliation import SessionReconciler
from octower.recovery.journal import RecoveryJournal
from octower.adapters.native_opencode import NativeOpenCodeAdapter
from octower.models import AgentState, ThresholdConfig
from octower.runtime import HttpHealthProbe, RehydrationAdapter, SubprocessRunner, TuiNop
from octower.state.classifier import AgentStateClassifier
from octower.supervisor.backend import BackendConfig, BackendDependencies, BackendProcess
from octower.supervisor.launcher import (
    HostPlatform,
    LaunchIdentity,
    LauncherConfig,
    allocate_localhost_port,
    build_launch_plan,
    resolve_opencode_executable,
)
from octower.supervisor.process import ProcessStartError


_ROOT_SESSION_ID: Final = "root"
_STATUS_SECONDS: Final = 5.0


def _ts() -> str:
    return f"{time.strftime('%H:%M:%S')}"


@dataclass(frozen=True, slots=True)
class StartOptions:
    """Parsed inputs for one localhost runtime instance."""

    project: Path
    port: int | None
    fast: bool = False
    isolated: bool = False
    launch: bool = False


class _MonotonicClock:
    def now(self) -> float:
        return time.monotonic()


def _parse_args() -> StartOptions:
    parser = argparse.ArgumentParser(prog="python -m octower")
    parser.add_argument("command", nargs="?", default="start", choices=("start",))
    parser.add_argument("--port", type=int)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--fast", action="store_true", help="Shorten 5/10/15 min thresholds to seconds for testing")
    parser.add_argument("--isolated", action="store_true", help="Use a temp isolated data directory (no API keys)")
    parser.add_argument("--launch", action="store_true", help="Open a new Windows Terminal tab for attach after startup")
    namespace = parser.parse_args()
    return StartOptions(namespace.project.resolve(), namespace.port, namespace.fast, namespace.isolated, namespace.launch)


def _print_instructions(endpoint: str, port: int, fast: bool = False) -> None:
    print(f"[{_ts()} octower] Server starting on {endpoint}")
    print(f"[{_ts()} octower] To send a task: opencode attach {endpoint}")
    print(f"[{_ts()} octower] To check health: curl {endpoint}/global/health")
    if fast:
        print(f"[{_ts()} octower] FAST MODE: 5s slow, 10s suspect, 15s auto-resume")
    else:
        print(f"[{_ts()} octower] Monitoring for stalls... (5min slow, 10min suspect, 15min auto-resume)")
    print(f"[{_ts()} octower] Local port: {port}")


async def _run_backend(
    backend: BackendProcess,
    stopped: anyio.Event,
) -> None:
    try:
        await backend.run()
    finally:
        stopped.set()


async def _print_status(backend: BackendProcess) -> None:
    while True:
        report = backend.report
        print(
            f"[{_ts()} octower] state={report.state.value} failures={report.consecutive_failures} "
            f"restarts={report.restarts} reason={report.reason}"
        )
        await anyio.sleep(_STATUS_SECONDS)


async def _monitor_sessions(
    client: OpenCodeClient,
    evidence_adapter: NativeOpenCodeAdapter,
    classifier: AgentStateClassifier,
    started_at: float,
) -> None:
    """Continuous session stall detection with same-session auto-resume."""

    initial_ids: set[str] = set()
    first_poll = True
    tracked: dict[str, float] = {}
    while True:
        try:
            sessions = await anyio.to_thread.run_sync(client.list_sessions)
        except Exception:
            await anyio.sleep(_STATUS_SECONDS)
            continue
        now = time.time()
        ids_now = {s.id for s in sessions}
        if first_poll:
            initial_ids = ids_now
            first_poll = False
            print(f"[{_ts()} octower] initial poll: {len(initial_ids)} existing sessions, waiting for new...")
            await anyio.sleep(_STATUS_SECONDS)
            continue
        new_ids = ids_now - initial_ids
        for sid in new_ids - set(initial_ids.union(tracked)):
            tracked[sid] = now
            print(f"[{_ts()} octower] session {sid}: new session detected")
        for sid, first_seen in list(tracked.items()):
            age = now - first_seen
            try:
                evidence = await anyio.to_thread.run_sync(evidence_adapter.get_evidence, sid)
            except Exception:
                del tracked[sid]
                continue
            if evidence.status == "busy" and not evidence.final_assistant_completed:
                tracked[sid] = now
                continue
            if age > 15:
                try:
                    evidence = await anyio.to_thread.run_sync(evidence_adapter.get_evidence, sid)
                except Exception:
                    del tracked[sid]
                    continue
                if evidence.final_assistant_completed:
                    print(f"[{_ts()} octower] session {sid}: task complete, awaiting user")
                    del tracked[sid]
                    continue
                print(f"[{_ts()} octower] session {sid}: stalled {age:.0f}s, recovering...")
                await _recover_session(client, sid)
                del tracked[sid]
        await anyio.sleep(_STATUS_SECONDS)
async def _recover_session(client: OpenCodeClient, session_id: str) -> None:
    """Abort and resume the same session to auto-recover from a stall."""
    try:
        await anyio.to_thread.run_sync(client.abort, session_id)
        await anyio.sleep(0.5)
        msg = (
            "You were unresponsive. "
            "If you were in the middle of a task, pick up exactly where you left off. "
            "If the conversation already finished and there is nothing pending, "
            "just say 'Ready.' and wait silently."
        )
        await anyio.to_thread.run_sync(client.prompt_async, session_id, msg)
        print(f"[{_ts()} octower] recovery sent to {session_id}")
    except Exception as exc:
        print(f"[{_ts()} octower] recovery failed for {session_id}: {exc}")


def _detect_platform() -> HostPlatform:
    """Auto-detect WSL2 vs native Windows at runtime."""
    if "WSL_DISTRO_NAME" in os.environ or "WSL_INTEROP" in os.environ:
        return HostPlatform.WSL2
    return HostPlatform.WINDOWS


def _ensure_tmux() -> None:
    """Auto-install tmux on WSL2 if missing."""
    import subprocess as _sp
    if _sp.run(["which", "tmux"], capture_output=True).returncode != 0:
        print(f"[{_ts()} octower] tmux not found, installing...")
        _sp.run(["sudo", "apt-get", "update", "-qq"], check=False)
        _sp.run(["sudo", "apt-get", "install", "-y", "-qq", "tmux"], check=True)
        print(f"[{_ts()} octower] tmux installed")


async def _open_attach_tab(backend: BackendProcess, client: OpenCodeClient) -> None:
    """Wait for backend healthy, then open a terminal window/tab for attach."""
    import subprocess as _sp
    while backend.report.state.value not in ("healthy",):
        await anyio.sleep(1)
    port = int(backend.endpoint.split(":")[-1])
    name = Path.cwd().name
    tab_title = name if len(name) <= 25 else name[:24] + "…"
    platform = _detect_platform()
    exe = resolve_opencode_executable(platform)

    if platform is HostPlatform.WSL2:
        _ensure_tmux()
        ts = time.strftime("%H%M%S")
        session = f"octower-{ts}"
        _sp.run(["tmux", "new-session", "-d", "-s", session, "-n", "octower",
                 exe, "attach", f"http://127.0.0.1:{port}"], check=False)
        _sp.run(["tmux", "rename-window", "-t", f"{session}:octower", tab_title], check=False)
        print(f"[{_ts()} octower] tmux session {session} created")
        if "WT_SESSION" in os.environ:
            _sp.run(
                ["wt.exe", "-w", "0", "new-tab", "--title", tab_title, "--suppressApplicationTitle",
                 "wsl.exe", "-d", "~", "--", "bash", "-c", f"tmux attach -t {session}"],
                check=False,
            )
            print(f"[{_ts()} octower] Windows Terminal tab opened")
        else:
            print(f"[{_ts()} octower] attach: tmux attach -t {session}")
    else:
        ps_cmd = f"& '{exe}' attach http://127.0.0.1:{port}"
        _sp.Popen(
            ["wt", "-w", "0", "new-tab", "--title", tab_title, "--suppressApplicationTitle",
             "powershell", "-NoExit", "-Command", ps_cmd],
            cwd=Path.cwd(),
        )
        print(f"[{_ts()} octower] attach tab opened on port {port}")


async def _monitor(backend: BackendProcess, client: OpenCodeClient, classifier: AgentStateClassifier, started_at: float, launch: bool = False) -> None:
    stopped = anyio.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        backend.request_stop()

    previous_interrupt = signal.signal(signal.SIGINT, request_stop)
    previous_terminate = signal.signal(signal.SIGTERM, request_stop)
    try:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(_run_backend, backend, stopped)
            task_group.start_soon(_print_status, backend)
            task_group.start_soon(_monitor_sessions, client, NativeOpenCodeAdapter(client), classifier, started_at)
            if launch:
                task_group.start_soon(_open_attach_tab, backend, client)
            await stopped.wait()
            task_group.cancel_scope.cancel()
    finally:
        signal.signal(signal.SIGINT, previous_interrupt)
        signal.signal(signal.SIGTERM, previous_terminate)


async def _async_main(options: StartOptions, data_dir: Path) -> None:
    port = options.port if options.port is not None else allocate_localhost_port()
    executable = resolve_opencode_executable(_detect_platform())
    plan = build_launch_plan(
        LauncherConfig(options.project, _ROOT_SESSION_ID, platform=_detect_platform()),
        LaunchIdentity(port, f"octower-{uuid4().hex}"),
        executable,
    )
    environment = {**os.environ}
    if options.isolated:
        environment["XDG_DATA_HOME"] = str(data_dir)
        print(f"[{_ts()} octower] Isolated data dir: {data_dir}")
    client = OpenCodeClient(plan.endpoint, timeout=2.0)
    health = HttpHealthProbe(timeout=2.0)
    journal = RecoveryJournal(data_dir / "octower" / "recovery.jsonl")
    thresholds = ThresholdConfig(slow_seconds=5, suspect_seconds=10, stall_seconds=15, stall_confirm_seconds=2, stall_confirm_samples=2) if options.fast else ThresholdConfig()
    platform = _detect_platform()
    health_timeout = 10.0 if platform is HostPlatform.WSL2 else 2.0
    shutdown_timeout = 10.0 if platform is HostPlatform.WSL2 else 5.0
    rehydration = RehydrationAdapter(
        client,
        SessionReconciler(_ROOT_SESSION_ID, client),
        AgentStateClassifier(_MonotonicClock(), thresholds),
        journal,
        _ROOT_SESSION_ID,
    )
    backend = BackendProcess(
        BackendConfig(
            plan,
            _ROOT_SESSION_ID,
            failure_threshold=3,
            max_restarts=2,
            health_timeout=health_timeout,
            restart_timeout=30.0,
            poll_seconds=2.0 if options.fast else 5.0,
            shutdown_timeout=shutdown_timeout,
        ),
        BackendDependencies(SubprocessRunner(environment), health, rehydration, TuiNop()),
    )
    _print_instructions(plan.endpoint, port, options.fast)
    started_at = time.time()
    try:
        await _monitor(backend, client, AgentStateClassifier(_MonotonicClock(), thresholds), started_at, launch=options.launch)
    finally:
        client.close()
        await health.aclose()
    print(f"[{_ts()} octower] Final state: {backend.report.state.value}")


def main() -> None:
    """Run the real localhost supervisor until interrupted."""
    options = _parse_args()
    try:
        with tempfile.TemporaryDirectory(prefix="octower-data-") as data_dir:
            anyio.run(_async_main, options, Path(data_dir))
    except KeyboardInterrupt:
        print(f"[{_ts()} octower] Interrupted; backend cleanup completed")
    except ProcessStartError as error:
        print(f"[{_ts()} octower] {error}")

