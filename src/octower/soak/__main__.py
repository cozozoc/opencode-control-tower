"""Phase 8 CLI; deterministic mock is authoritative because safely inducing provider hangs in a real backend requires external credentials and non-reproducible service control."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from octower.soak.scenarios import REQUIRED_SCENARIOS, run_scenario


def main(arguments: tuple[str, ...] | None = None) -> int:
    """Run selected soak scenarios and return success only for zero violations."""
    selected = arguments if arguments else REQUIRED_SCENARIOS
    unknown = tuple(name for name in selected if name not in REQUIRED_SCENARIOS)
    if unknown:
        print(f"unknown scenario(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    with TemporaryDirectory(prefix="octower-soak-") as directory:
        results = tuple(
            run_scenario(name, Path(directory) / name) for name in selected
        )
    for result in results:
        print(result.report.render())
        for violation in result.report.violations:
            print(f"  violation: {violation}")
    print(
        "TOTAL: "
        f"scenarios={len(results)} "
        f"sessions={sum(result.report.discovered_sessions for result in results)} "
        f"done={sum(result.report.done_count for result in results)} "
        f"recoveries={sum(result.report.recovery_attempts for result in results)} "
        f"resumes={sum(result.report.resume_count for result in results)} "
        f"aborts={sum(result.report.aborts for result in results)} "
        f"stall_confirmations={sum(result.report.stall_confirmations for result in results)} "
        f"parent_protections={sum(result.report.parent_protection_events for result in results)} "
        f"journal_replays={sum(result.report.journal_replays for result in results)} "
        f"backend_restarts={sum(result.report.backend_restarts for result in results)} "
        f"false_aborts={sum(result.report.false_aborts for result in results)} "
        f"violations={sum(len(result.report.violations) for result in results)}"
    )
    return 0 if all(result.report.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(tuple(sys.argv[1:])))
