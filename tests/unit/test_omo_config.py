from __future__ import annotations

from pathlib import Path

from octower.omo.config import (
    DEFAULT_STALE_TIMEOUT_MS,
    ConfigValueSource,
    OmoConfigIO,
    discover_omo_config,
    resolve_stale_timeout,
)


def test_modern_config_beats_legacy_config() -> None:
    home = Path("C:/Users/tester")
    modern = home / ".omo/omo.jsonc"
    legacy = home / "oh-my-openagent.json"
    files = {
        modern: '{"background_task": {"staleTimeoutMs": 600000}}',
        legacy: '{"background_task": {"staleTimeoutMs": 1800000}}',
    }
    io = OmoConfigIO(files.__contains__, files.__getitem__)

    discovery = discover_omo_config(home, None, io)
    resolved = resolve_stale_timeout(discovery)

    assert discovery.config_path == modern
    assert resolved.value_ms == 600000
    assert resolved.source_path == modern


def test_project_overlay_takes_precedence_over_home_config() -> None:
    home = Path("C:/Users/tester")
    project = Path("C:/work/project")
    base = home / ".omo/omo.jsonc"
    overlay = project / ".omo/opencode.jsonc"
    files = {
        base: '{"background_task": {"staleTimeoutMs": 600000}}',
        overlay: '{"background_task": {"staleTimeoutMs": 1800000}}',
    }

    discovery = discover_omo_config(
        home, project, OmoConfigIO(files.__contains__, files.__getitem__)
    )
    resolved = resolve_stale_timeout(discovery)

    assert discovery.config_path == overlay
    assert resolved.value_ms == 1800000
    assert resolved.source_path == overlay


def test_project_overlay_without_background_task_inherits_home_value() -> None:
    home = Path("C:/Users/tester")
    project = Path("C:/work/project")
    base = home / ".omo/omo.jsonc"
    overlay = project / ".omo/omo.jsonc"
    files = {
        base: '{"background_task": {"staleTimeoutMs": 600000}}',
        overlay: '{"agents": {}}',
    }

    discovery = discover_omo_config(
        home, project, OmoConfigIO(files.__contains__, files.__getitem__)
    )
    resolved = resolve_stale_timeout(discovery)

    assert discovery.config_path == overlay
    assert resolved.value_ms == 600000
    assert resolved.source_path == base


def test_jsonc_line_comments_preserve_double_slash_inside_strings(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config = home / ".omo/omo.jsonc"
    config.parent.mkdir(parents=True)
    config.write_text(
        """// config comment
        {
          "$schema": "https://example.test/schema.json", // inline comment
          "background_task": {"staleTimeoutMs": 600000}
        }
        """,
        encoding="utf-8",
    )

    discovery = discover_omo_config(home, None)
    resolved = resolve_stale_timeout(discovery)

    assert resolved.value_ms == 600000


def test_absent_background_task_uses_documented_default() -> None:
    home = Path("C:/Users/tester")
    modern = home / ".omo/omo.jsonc"
    files = {modern: '{"agents": {}}'}

    discovery = discover_omo_config(
        home, None, OmoConfigIO(files.__contains__, files.__getitem__)
    )
    resolved = resolve_stale_timeout(discovery)

    assert resolved.value_ms == DEFAULT_STALE_TIMEOUT_MS == 180000
    assert resolved.source is ConfigValueSource.DEFAULT
    assert resolved.source_path is None
    assert resolved.raw_config_available is True


def test_no_config_uses_documented_default_without_raw_config() -> None:
    io = OmoConfigIO(lambda _path: False, lambda _path: "")

    resolved = resolve_stale_timeout(
        discover_omo_config(Path("C:/Users/tester"), None, io)
    )

    assert resolved.value_ms == 180000
    assert resolved.raw_config_available is False
