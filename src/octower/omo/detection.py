"""Read-only OmO installation and version detection for Phase 6 (§3, §21)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import shutil


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class OmoDetectionIO:
    """Injected filesystem and PATH operations used by installation detection."""

    path_exists: Callable[[Path], bool] = Path.is_file
    read_text: Callable[[Path], str] = _read_text
    which: Callable[[str], str | None] = shutil.which


@dataclass(frozen=True, slots=True)
class OmoInstallation:
    """Detected OmO package or CLI identity without process execution."""

    detected: bool
    version: str | None
    package_json_path: Path | None
    executable_path: str | None

    @property
    def package_path(self) -> Path | None:
        return self.package_json_path


def detect_omo_installation(home: Path, io: OmoDetectionIO | None = None) -> OmoInstallation:
    """Detect package manifests first, then known OmO CLI names without running them."""
    sources = io or OmoDetectionIO()
    package_root = home / ".cache" / "opencode" / "packages" / "oh-my-openagent@latest"
    manifests = (
        package_root / "package.json",
        package_root / "node_modules" / "oh-my-openagent" / "package.json",
    )
    executable = next(
        (resolved for command in ("omo", "oh-my-openagent") if (resolved := sources.which(command))),
        None,
    )
    for manifest in manifests:
        if sources.path_exists(manifest):
            return OmoInstallation(
                detected=True,
                version=_manifest_version(sources.read_text(manifest)),
                package_json_path=manifest,
                executable_path=executable,
            )
    if executable is not None:
        return OmoInstallation(True, None, None, executable)
    return OmoInstallation(False, None, None, None)


def _manifest_version(raw: str) -> str | None:
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    if isinstance(version, str):
        return version
    dependencies = data.get("dependencies")
    if not isinstance(dependencies, dict):
        return None
    dependency_version = dependencies.get("oh-my-openagent")
    return dependency_version if isinstance(dependency_version, str) else None
