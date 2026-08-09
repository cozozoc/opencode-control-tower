from __future__ import annotations

from dataclasses import replace

import pytest

from octower.models import SessionEvidence


class FakeClock:
    """Deterministic monotonic clock for §25 state-machine tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def advance_minutes(self, minutes: float) -> None:
        self.advance(minutes * 60)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def evidence(**changes: object) -> SessionEvidence:
    """Build safe unfinished idle evidence; callers override only relevant facts."""
    base = SessionEvidence(
        session_id="ses-child",
        status="idle",
        last_semantic_activity=0.0,
        final_assistant_completed=False,
    )
    return replace(base, **changes)
