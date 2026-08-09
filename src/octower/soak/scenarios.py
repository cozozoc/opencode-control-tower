"""Named deterministic soak cases from handoff §24 and INV-001..010."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

from octower.models import AgentState
from octower.omo.policy import OmoPolicyConflict, evaluate_policy
from octower.soak.harness import ScenarioResult, SoakHarness
from octower.soak.provider import (
    HumanWaitKind,
    ScriptedEvent,
    SessionScript,
)
from octower.soak.scenario_support import build_harness, failed_checks, run_protected
from octower.soak.supervisor_case import run_backend_restart_case


ScenarioRunner = Callable[[Path], ScenarioResult]


def _fast_success(path: Path) -> ScenarioResult:
    harness = build_harness(
        path,
        SessionScript(
            "fast-child",
            "root",
            (
                ScriptedEvent(0, status="busy"),
                ScriptedEvent(30, status="idle", final_assistant_completed=True),
            ),
        ),
    )
    harness.sample()
    harness.advance_and_sample(30)
    result = harness.result("fast_success")
    violations = failed_checks(
        (result.state_for("fast-child") is AgentState.DONE, "fast child did not finish"),
        (result.report.aborts == 0, "fast child was aborted"),
    )
    return harness.result("fast_success", violations=violations)


def _delayed_success(path: Path) -> ScenarioResult:
    harness = build_harness(
        path,
        SessionScript(
            "delayed-child",
            "root",
            (
                ScriptedEvent(0, status="busy"),
                ScriptedEvent(700, status="idle", final_assistant_completed=True),
            ),
        ),
    )
    harness.sample()
    harness.advance_and_sample(350)
    harness.advance_and_sample(350)
    result = harness.result("delayed_success")
    violations = failed_checks(
        (result.state_for("delayed-child") is AgentState.DONE, "delayed child did not finish"),
        (result.report.aborts == 0, "delayed child was aborted"),
    )
    return harness.result("delayed_success", violations=violations)


def _parent_protected(path: Path) -> ScenarioResult:
    parent = SessionScript("parent", "root", (ScriptedEvent(0, status="busy"),))
    child = SessionScript(
        "active-child",
        "parent",
        (ScriptedEvent(0, status="retry", provider_retry=True),),
    )
    harness = build_harness(path, parent, child)
    harness.advance_and_sample(1_000)
    result = harness.result("parent_protected_while_descendants_active")
    violations = failed_checks(
        (result.report.parent_protection_events >= 1, "active descendant did not protect parent"),
        (result.report.aborts == 0, "protected parent was aborted"),
    )
    return harness.result(result.report.scenario, violations=violations)


def _soft_resume(path: Path) -> ScenarioResult:
    harness = build_harness(
        path,
        SessionScript("idle-child", "root", (ScriptedEvent(0, status="idle"),)),
    )
    harness.advance_and_sample(660)
    harness.advance_and_sample(2)
    result = harness.result("idle_unfinished_soft_resume")
    violations = failed_checks(
        (result.report.aborts == 0, "soft resume performed an abort"),
        (result.report.resume_count == 1, "soft resume count was not one"),
        (result.state_for("idle-child") is AgentState.RUNNING, "soft resume produced no activity"),
    )
    return harness.result(result.report.scenario, violations=violations)


def _hard_stall(path: Path) -> ScenarioResult:
    harness = build_harness(
        path,
        SessionScript("hard-stall", "root", (ScriptedEvent(0, status="busy"),)),
    )
    harness.advance_and_sample(901)
    for _sample in range(3):
        harness.advance_and_sample(20)
    harness.advance_and_sample(2)
    result = harness.result("busy_hard_stall")
    violations = failed_checks(
        (result.report.aborts == 1, "hard stall abort count was not one"),
        (result.report.resume_count == 1, "hard stall resume count was not one"),
        (result.state_for("hard-stall") is AgentState.RUNNING, "hard stall did not recover"),
    )
    return harness.result(result.report.scenario, violations=violations)


def _done_never_stalls(path: Path) -> ScenarioResult:
    harness = build_harness(
        path,
        SessionScript(
            "done-child",
            "root",
            (ScriptedEvent(0, status="idle", final_assistant_completed=True),),
        ),
    )
    harness.advance_and_sample(1_800)
    harness.advance_and_sample(1_800)
    result = harness.result("done_never_stalls")
    child_states = tuple(
        transition.current
        for transition in result.report.metrics.transitions
        if transition.session_id == "done-child"
    )
    violations = failed_checks(
        (child_states == (AgentState.DONE,), "DONE child entered another state"),
        (result.report.aborts == 0, "DONE child was aborted"),
    )
    return harness.result(result.report.scenario, violations=violations)


def _nested(path: Path) -> ScenarioResult:
    parent = SessionScript("parent", "root", (ScriptedEvent(0, status="idle"),))
    grandchild = SessionScript(
        "grandchild",
        "parent",
        (
            ScriptedEvent(0, status="busy"),
            ScriptedEvent(970, status="idle", final_assistant_completed=True),
        ),
    )
    harness = build_harness(path, parent, grandchild)
    harness.advance_and_sample(901)
    for _sample in range(3):
        harness.advance_and_sample(20)
    harness.advance_and_sample(10)
    result = harness.result("nested_children")
    violations = failed_checks(
        (result.report.discovered_sessions == 3, "nested session discovery was incomplete"),
        (result.report.parent_protection_events >= 1, "nested parent was not protected"),
        (result.state_for("grandchild") is AgentState.DONE, "recovered grandchild did not finish"),
        ("parent" in result.resumed_session_ids, "parent orchestration was not resumed"),
    )
    return harness.result(result.report.scenario, violations=violations)


def _journal_replay(path: Path) -> ScenarioResult:
    script = SessionScript("replay-child", "root", (ScriptedEvent(0, status="idle"),))
    harness = build_harness(path, script)
    harness.advance_and_sample(660)
    harness.clock.advance(2)
    restarted = SoakHarness(
        "root", harness.provider, harness.journal.path, automatic_recovery_armed=True
    )
    restarted.replay()
    result = restarted.result("guardian_restart_journal_replay")
    violations = failed_checks(
        (result.report.journal_replays == 1, "active journal was not replayed once"),
        (result.report.resume_count == 1, "journal replay duplicated resume"),
        (result.state_for("replay-child") is AgentState.RUNNING, "replay did not confirm activity"),
    )
    return restarted.result(result.report.scenario, violations=violations)


def _bounded(path: Path) -> ScenarioResult:
    script = SessionScript(
        "never-recovers",
        "root",
        (ScriptedEvent(0, status="idle"),),
        continuation_delay_seconds=10_000,
    )
    harness = build_harness(path, script)
    harness.advance_and_sample(660)
    harness.clock.advance(301)
    harness.recovery.poll("never-recovers")
    harness.clock.advance(301)
    terminal = harness.recovery.poll("never-recovers")
    harness.force_state("never-recovers", terminal.state)
    result = harness.result("bounded_attempts_failed")
    violations = failed_checks(
        (terminal.state is AgentState.FAILED_RECOVERY, "attempt budget was not terminal"),
        (result.report.recovery_attempts == 2, "recovery attempts were not bounded at two"),
    )
    return harness.result(result.report.scenario, violations=violations)


def _backend_restart(path: Path) -> ScenarioResult:
    harness = build_harness(path)
    harness.sample()
    restarts, resumed = run_backend_restart_case()
    violations = failed_checks(
        (restarts == 1, "backend did not restart once after three failures"),
        (resumed == ("active", "recovering"), "rehydration resumed historical sessions"),
    )
    return harness.result(
        "backend_restart_rehydration",
        violations=violations,
        backend_restarts=restarts,
        resumed_session_ids=resumed,
    )


def _omo_gate(path: Path) -> ScenarioResult:
    policy = evaluate_policy(180_000)
    harness = build_harness(
        path,
        SessionScript("omo-stall", "root", (ScriptedEvent(0, status="busy"),)),
        armed=policy.automatic_recovery_allowed,
    )
    harness.advance_and_sample(1_000)
    result = harness.result("omo_conflict_gate")
    violations = failed_checks(
        (policy.conflict is OmoPolicyConflict.CONFLICT_CRITICAL, "OmO conflict was not critical"),
        (not result.automatic_recovery_armed, "automatic recovery was armed under conflict"),
        (result.report.recovery_attempts == 0, "recovery ran despite OmO conflict"),
    )
    return harness.result(result.report.scenario, violations=violations)


_SCENARIOS: Final[dict[str, ScenarioRunner]] = {
    "fast_success": _fast_success,
    "delayed_success": _delayed_success,
    "retry_protected": lambda path: run_protected(
        path, "retry_protected", ScriptedEvent(0, status="retry", provider_retry=True)
    ),
    "running_tool_protected": lambda path: run_protected(
        path, "running_tool_protected", ScriptedEvent(0, status="busy", tool_running=True)
    ),
    "human_wait_protected": lambda path: run_protected(
        path,
        "human_wait_protected",
        ScriptedEvent(0, status="idle", human_wait_kind=HumanWaitKind.QUESTION),
    ),
    "parent_protected_while_descendants_active": _parent_protected,
    "idle_unfinished_soft_resume": _soft_resume,
    "busy_hard_stall": _hard_stall,
    "done_never_stalls": _done_never_stalls,
    "nested_children": _nested,
    "backend_restart_rehydration": _backend_restart,
    "bounded_attempts_failed": _bounded,
    "guardian_restart_journal_replay": _journal_replay,
    "omo_conflict_gate": _omo_gate,
}

REQUIRED_SCENARIOS: Final = tuple(_SCENARIOS)


def run_scenario(name: str, journal_directory: Path) -> ScenarioResult:
    """Run one named scenario with an accelerated clock and isolated journal."""
    journal_directory.mkdir(parents=True, exist_ok=True)
    return _SCENARIOS[name](journal_directory)
