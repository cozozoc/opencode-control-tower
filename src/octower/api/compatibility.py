"""Version and advisory-status compatibility for OpenCode 1.18.15 (§2.4)."""

from __future__ import annotations

from dataclasses import dataclass
import warnings

from octower.api.opencode import Health, OpenCodeClient

SUPPORTED_MINIMUM_VERSION = "1.18.15"


@dataclass(frozen=True, slots=True)
class SessionStatus:
    """ADVISORY-only session status; it never independently proves DONE or STALL."""

    type: str
    attempt: int | None = None
    message: str | None = None
    next: float | None = None


class OpenCodeCompatibility:
    """Contain version drift and unreliable ``/session/status`` behavior (§2.4)."""

    def __init__(self, client: OpenCodeClient, supported_minimum: str = SUPPORTED_MINIMUM_VERSION) -> None:
        self._client = client
        self._supported_minimum = supported_minimum

    def detect_version(self) -> Health:
        """Read health and warn when the tested server version differs (§2.1)."""
        health = self._client.health()
        if health.version != self._supported_minimum:
            warnings.warn(
                f"OpenCode {health.version or 'unknown'} differs from supported {self._supported_minimum}",
                RuntimeWarning,
                stacklevel=2,
            )
        return health

    def session_status(self) -> dict[str, SessionStatus]:
        """Read the advisory map; `{}` is expected for idle sessions in 1.18.15."""
        return {
            session_id: _status(value)
            for session_id, value in self._client.get_session_status().items()
            if isinstance(value, dict)
        }

    def status_enrichment(self, session_id: str) -> SessionStatus | None:
        """Return fresh optional advice without inferring idle, DONE, or STALL (INV-007)."""
        return self.session_status().get(session_id)


def _status(data: dict[str, object]) -> SessionStatus:
    next_value = data.get("next")
    return SessionStatus(
        type=str(data.get("type", "")),
        attempt=data.get("attempt") if isinstance(data.get("attempt"), int) else None,
        message=data.get("message") if isinstance(data.get("message"), str) else None,
        next=float(next_value) if isinstance(next_value, (int, float)) else None,
    )
