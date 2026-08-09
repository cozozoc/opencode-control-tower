"""Shared deterministic fixtures for named Phase 8 scenarios."""

from __future__ import annotations

from pathlib import Path

from octower.soak.harness import ScenarioResult, SoakHarness
from octower.soak.provider import (
    DeterministicProvider,
    ManualClock,
    ScriptedEvent,
    SessionScript,
)


def build_harness(
    path: Path, *scripts: SessionScript, armed: bool = True
) -> SoakHarness:
    root = SessionScript(
        "root", None, (ScriptedEvent(0, status="retry", provider_retry=True),)
    )
    provider = DeterministicProvider(ManualClock(), (root, *scripts))
    return SoakHarness(
        "root", provider, path / "recovery.jsonl", automatic_recovery_armed=armed
    )


def failed_checks(*checks: tuple[bool, str]) -> tuple[str, ...]:
    return tuple(message for passed, message in checks if not passed)


def run_protected(path: Path, name: str, event: ScriptedEvent) -> ScenarioResult:
    session_id = (
        name.removesuffix("_protected").replace("running_tool", "tool").replace("_", "-")
    )
    harness = build_harness(path, SessionScript(session_id, "root", (event,)))
    harness.advance_and_sample(1_500)
    result = harness.result(name)
    violations = failed_checks(
        (result.report.aborts == 0, f"{session_id} was aborted"),
        (result.report.resume_count == 0, f"{session_id} was nudged"),
    )
    return harness.result(name, violations=violations)
