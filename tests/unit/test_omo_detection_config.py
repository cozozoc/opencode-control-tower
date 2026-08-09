from __future__ import annotations

from pathlib import Path

from octower.omo.config import (
    DEFAULT_STALE_TIMEOUT_MS,
    ConfigIO,
    StaleTimeoutSource,
    discover_omo_config,
    parse_omo_config,
    resolve_stale_timeout,
)
from octower.omo.installation import DetectionIO, detect_omo_installation


def test_installation_reads_version_from_verified_package_json() -> None:
    home = Path("C:/Users/tester")
    package_path = home / ".cache/opencode/packages/oh-my-openagent@latest/package.json"
    io = DetectionIO(
        path_exists=lambda path: path == package_path,
        read_text=lambda _path: '{"name":"oh-my-openagent","version":"4.19.4"}',
        which=lambda _name: None,
    )

    installation = detect_omo_installation(home, io)

    assert installation.detected is True
    assert installation.version == "4.19.4"
    assert installation.package_json_path == package_path
    assert installation.executable_path is None


def test_installation_uses_nested_package_layout_and_cli_fallback() -> None:
    home = Path("C:/Users/tester")
    nested = (
        home
        / ".cache/opencode/packages/oh-my-openagent@latest/node_modules/oh-my-openagent/package.json"
    )
    io = DetectionIO(
        path_exists=lambda path: path == nested,
        read_text=lambda _path: '{"version":"4.20.0"}',
        which=lambda name: "C:/bin/omo.exe" if name == "omo" else None,
    )

    installation = detect_omo_installation(home, io)

    assert installation.version == "4.20.0"
    assert installation.package_json_path == nested
    assert installation.executable_path == "C:/bin/omo.exe"


def test_installation_detects_cli_without_package_and_reports_absence() -> None:
    home = Path("C:/Users/tester")
    cli_only = detect_omo_installation(
        home,
        DetectionIO(
            path_exists=lambda _path: False,
            read_text=lambda _path: "",
            which=lambda name: "C:/bin/oh-my-openagent.exe"
            if name == "oh-my-openagent"
            else None,
        ),
    )
    absent = detect_omo_installation(
        home,
        DetectionIO(
            path_exists=lambda _path: False,
            read_text=lambda _path: "",
            which=lambda _name: None,
        ),
    )

    assert cli_only.detected is True
    assert cli_only.version is None
    assert cli_only.executable_path == "C:/bin/oh-my-openagent.exe"
    assert absent.detected is False


def test_modern_config_beats_legacy_config() -> None:
    home = Path("C:/Users/tester")
    modern = home / ".omo/omo.jsonc"
    legacy = home / "oh-my-openagent.json"
    texts = {
        modern: '{"background_task":{"staleTimeoutMs":1800000}}',
        legacy: '{"background_task":{"staleTimeoutMs":180000}}',
    }
    io = ConfigIO(path_exists=texts.__contains__, read_text=texts.__getitem__)

    config = discover_omo_config(home, None, io)

    assert config is not None
    assert config.path == modern
    assert resolve_stale_timeout(config).value_ms == 1800000


def test_project_overlay_has_effective_precedence_over_home_config() -> None:
    home = Path("C:/Users/tester")
    project = Path("C:/work/repo")
    overlay = project / ".omo/omo.jsonc"
    modern = home / ".omo/omo.jsonc"
    texts = {
        modern: '{"background_task":{"staleTimeoutMs":180000}}',
        overlay: '{"background_task":{"staleTimeoutMs":1800000}}',
    }

    config = discover_omo_config(
        home,
        project,
        ConfigIO(path_exists=texts.__contains__, read_text=texts.__getitem__),
    )

    assert config is not None
    assert config.path == overlay
    assert resolve_stale_timeout(config).value_ms == 1800000


def test_jsonc_parser_preserves_comment_tokens_inside_strings() -> None:
    path = Path("C:/Users/tester/.omo/omo.jsonc")
    text = """
    {
      // OmO policy
      "schema": "https://example.test/schema//v1",
      "note": "literal /* text */ is not a comment",
      "background_task": {
        "staleTimeoutMs": 600000, /* Guardian remains authoritative */
      },
    }
    """

    config = parse_omo_config(path, text)

    assert config.background_task is not None
    assert config.background_task.stale_timeout_ms == 600000


def test_stale_timeout_uses_config_value_or_documented_default() -> None:
    path = Path("C:/Users/tester/.omo/omo.jsonc")
    explicit = resolve_stale_timeout(
        parse_omo_config(path, '{"background_task":{"staleTimeoutMs":1800000}}')
    )
    absent_block = resolve_stale_timeout(parse_omo_config(path, '{"agents":{}}'))
    missing_file = resolve_stale_timeout(None)

    assert explicit.value_ms == 1800000
    assert explicit.source is StaleTimeoutSource.CONFIG
    assert explicit.raw_config_available is True
    assert absent_block.value_ms == DEFAULT_STALE_TIMEOUT_MS
    assert absent_block.source is StaleTimeoutSource.DEFAULT
    assert absent_block.raw_config_available is True
    assert missing_file.value_ms == DEFAULT_STALE_TIMEOUT_MS
    assert missing_file.raw_config_available is False


def test_config_discovery_reads_real_tmp_path_without_mutating_it(tmp_path: Path) -> None:
    config_path = tmp_path / ".omo" / "omo.jsonc"
    config_path.parent.mkdir()
    original = '{"background_task":{"staleTimeoutMs":1800000}}'
    config_path.write_text(original, encoding="utf-8")

    config = discover_omo_config(tmp_path, None)

    assert config is not None
    assert resolve_stale_timeout(config).value_ms == 1800000
    assert config_path.read_text(encoding="utf-8") == original
