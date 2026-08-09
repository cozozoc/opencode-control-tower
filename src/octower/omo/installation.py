"""Stable Phase 6 public names for read-only OmO installation detection."""

from .detection import OmoDetectionIO, OmoInstallation, detect_omo_installation

DetectionIO = OmoDetectionIO

__all__ = ["DetectionIO", "OmoInstallation", "detect_omo_installation"]
