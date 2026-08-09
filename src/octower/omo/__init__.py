"""Read-only OmO compatibility adapter for Phase 6 (§3, §21)."""

from .config import ResolvedStaleTimeout, discover_omo_config, resolve_stale_timeout
from .detection import OmoInstallation, detect_omo_installation
from .doctor import DoctorReport, build_doctor_report
from .policy import OmoPolicyConflict, build_patch_suggestion, evaluate_policy_conflict

__all__ = [
    "DoctorReport",
    "OmoInstallation",
    "OmoPolicyConflict",
    "ResolvedStaleTimeout",
    "build_doctor_report",
    "build_patch_suggestion",
    "detect_omo_installation",
    "discover_omo_config",
    "evaluate_policy_conflict",
    "resolve_stale_timeout",
]
