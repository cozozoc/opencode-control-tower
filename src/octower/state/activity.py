"""Semantic activity tracking that excludes display-only churn (§9)."""

from __future__ import annotations

from octower.models import Clock, SemanticActivityRecord


_NON_SEMANTIC_KINDS = frozenset(
    {"cursor", "spinner", "refresh", "elapsed_text", "pane_redraw", "unchanged_poll"}
)


class SemanticActivityTracker:
    """Track the last distinct semantic observation for one session (§9)."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._last_activity: float | None = None
        self._last_fingerprint_by_kind: dict[str, str] = {}

    @property
    def last_activity(self) -> float | None:
        """Return the latest timestamp that represents actual agent progress."""
        return self._last_activity

    def observe(self, kind: str, fingerprint: str) -> SemanticActivityRecord | None:
        """Record a new semantic event, ignoring visual churn and repeated polls (§9)."""
        if kind in _NON_SEMANTIC_KINDS:
            return None
        if self._last_fingerprint_by_kind.get(kind) == fingerprint:
            return None
        occurred_at = self._clock.now()
        self._last_fingerprint_by_kind[kind] = fingerprint
        self._last_activity = occurred_at
        return SemanticActivityRecord(kind, fingerprint, occurred_at)
