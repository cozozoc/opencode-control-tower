from __future__ import annotations

from pathlib import Path

from octower.omo.detection import OmoDetectionIO, detect_omo_installation


def test_package_manifest_detects_omo_and_reads_version() -> None:
    home = Path("C:/Users/tester")
    package = home / ".cache/opencode/packages/oh-my-openagent@latest/package.json"
    files = {package: '{"version": "4.19.4"}'}
    io = OmoDetectionIO(
        path_exists=files.__contains__,
        read_text=files.__getitem__,
        which=lambda _name: None,
    )

    installation = detect_omo_installation(home, io)

    assert installation.detected is True
    assert installation.version == "4.19.4"
    assert installation.package_path == package


def test_wrapper_manifest_dependency_supplies_fallback_version() -> None:
    home = Path("C:/Users/tester")
    package = home / ".cache/opencode/packages/oh-my-openagent@latest/package.json"
    files = {package: '{"dependencies": {"oh-my-openagent": "4.19.4"}}'}
    io = OmoDetectionIO(files.__contains__, files.__getitem__, lambda _name: None)

    installation = detect_omo_installation(home, io)

    assert installation.version == "4.19.4"


def test_cli_path_detects_installation_without_manifest_version() -> None:
    io = OmoDetectionIO(
        path_exists=lambda _path: False,
        read_text=lambda _path: "",
        which=lambda name: "C:/bin/omo.exe" if name == "omo" else None,
    )

    installation = detect_omo_installation(Path("C:/Users/tester"), io)

    assert installation.detected is True
    assert installation.version is None
    assert installation.executable_path == "C:/bin/omo.exe"


def test_missing_manifest_and_cli_reports_not_detected() -> None:
    io = OmoDetectionIO(
        path_exists=lambda _path: False,
        read_text=lambda _path: "",
        which=lambda _name: None,
    )

    installation = detect_omo_installation(Path("C:/Users/tester"), io)

    assert installation.detected is False
    assert installation.version is None
    assert installation.package_path is None
    assert installation.executable_path is None
