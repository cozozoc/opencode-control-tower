"""Pure §21 doctor report composition over injected read-only sources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final, Protocol

from octower.api.compatibility import SUPPORTED_MINIMUM_VERSION
from octower.omo.config import ResolvedStaleTimeout
from octower.omo.detection import OmoInstallation
from octower.omo.policy import OmoPolicyConflict, evaluate_policy_conflict


REQUIRED_PYTHON_VERSION: Final = ">=3.11"
REQUIRED_TEXTUAL_VERSION: Final = "Phase 7 dependency not installed"


class OpenCodeApiCompatibility(str, Enum):
    """Compatibility against the OpenCode API version verified in Phase 1."""

    SUPPORTED = "supported"
    VERSION_DRIFT = "version_drift"
    UNKNOWN = "unknown"


class TmuxIntegration(str, Enum):
    """Optional visual integration state; never a Guardian stall signal."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"


class ServerHealth(str, Enum):
    """Doctor's injected OpenCode server health observation."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class DoctorSources(Protocol):
    """Read-only observations composed by ``build_doctor_report``."""

    def opencode_version(self) -> str | None: ...

    def omo_installation(self) -> OmoInstallation: ...

    def omo_stale_timeout(self) -> ResolvedStaleTimeout: ...

    def tmux_integration(self) -> TmuxIntegration: ...

    def server_health(self) -> ServerHealth: ...


@dataclass(frozen=True, slots=True)
class DoctorContext:
    """Invocation-specific root and project identity for §21 reporting."""

    project: Path
    root_session_id: str
    required_python_version: str = REQUIRED_PYTHON_VERSION
    required_textual_version: str = REQUIRED_TEXTUAL_VERSION


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Complete Phase 6 doctor data model; rendering belongs to Phase 7."""

    opencode_version: str | None
    api_compatibility: OpenCodeApiCompatibility
    omo_detected: bool
    omo_version: str | None
    omo_config_path: Path | None
    omo_stale_timeout_ms: int
    omo_conflict: OmoPolicyConflict
    tmux_integration: TmuxIntegration
    root_session_id: str
    project: Path
    server_health: ServerHealth
    required_python_version: str
    required_textual_version: str


def build_doctor_report(sources: DoctorSources, context: DoctorContext) -> DoctorReport:
    """Compose injected observations without performing config or process I/O."""
    version = sources.opencode_version()
    installation = sources.omo_installation()
    timeout = sources.omo_stale_timeout()
    conflict = (
        evaluate_policy_conflict(timeout.value_ms)
        if installation.detected
        else OmoPolicyConflict.OK
    )
    return DoctorReport(
        opencode_version=version,
        api_compatibility=_api_compatibility(version),
        omo_detected=installation.detected,
        omo_version=installation.version,
        omo_config_path=timeout.config_path,
        omo_stale_timeout_ms=timeout.value_ms,
        omo_conflict=conflict,
        tmux_integration=sources.tmux_integration(),
        root_session_id=context.root_session_id,
        project=context.project,
        server_health=sources.server_health(),
        required_python_version=context.required_python_version,
        required_textual_version=context.required_textual_version,
    )


def _api_compatibility(version: str | None) -> OpenCodeApiCompatibility:
    if version is None:
        return OpenCodeApiCompatibility.UNKNOWN
    if version == SUPPORTED_MINIMUM_VERSION:
        return OpenCodeApiCompatibility.SUPPORTED
    return OpenCodeApiCompatibility.VERSION_DRIFT
