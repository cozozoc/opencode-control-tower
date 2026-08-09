"""Read-only OmO config discovery and effective timeout resolution (§3, §21)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Final, assert_never


DEFAULT_STALE_TIMEOUT_MS: Final = 180_000


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class OmoConfigIO:
    """Injected read-only filesystem operations for deterministic config tests."""

    path_exists: Callable[[Path], bool] = Path.is_file
    read_text: Callable[[Path], str] = _read_text


ConfigIO = OmoConfigIO


@dataclass(frozen=True, slots=True)
class BackgroundTaskConfig:
    """Parsed timeout subset of OmO's background-task block."""

    stale_timeout_ms: int | None


@dataclass(frozen=True, slots=True)
class ParsedOmoConfig:
    """Only the OmO fields relevant to Guardian's timeout policy."""

    path: Path
    background_task_present: bool
    stale_timeout_ms: int | None

    @property
    def background_task(self) -> BackgroundTaskConfig | None:
        if not self.background_task_present:
            return None
        return BackgroundTaskConfig(self.stale_timeout_ms)


@dataclass(frozen=True, slots=True)
class OmoConfigDiscovery:
    """Discovered base and project overlay configs in effective merge order."""

    config_path: Path | None
    layers: tuple[ParsedOmoConfig, ...]

    @property
    def path(self) -> Path | None:
        return self.config_path


class ConfigValueSource(str, Enum):
    """Origin of the effective stale timeout."""

    CONFIG = "config"
    DEFAULT = "default"


StaleTimeoutSource = ConfigValueSource


@dataclass(frozen=True, slots=True)
class ResolvedStaleTimeout:
    """Effective OmO timeout plus provenance needed by doctor and startup gates."""

    value_ms: int
    source: ConfigValueSource
    config_path: Path | None
    raw_config_available: bool
    source_path: Path | None = None


def discover_omo_config(
    home: Path,
    project: Path | None,
    io: OmoConfigIO | None = None,
) -> OmoConfigDiscovery:
    """Discover one modern-or-legacy base and an optional higher-priority overlay."""
    sources = io or OmoConfigIO()
    modern = (home / ".omo" / "omo.jsonc", home / ".omo" / "omo.json")
    legacy = tuple(
        home / name
        for name in (
            "oh-my-openagent.jsonc",
            "oh-my-openagent.json",
            "oh-my-opencode.jsonc",
            "oh-my-opencode.json",
        )
    )
    base_path = _first_existing(modern, sources) or _first_existing(legacy, sources)
    overlay_path = None
    if project is not None:
        overlay_root = project / ".omo"
        overlay_path = _first_existing(
            (
                overlay_root / "omo.jsonc",
                overlay_root / "omo.json",
                overlay_root / "opencode.jsonc",
                overlay_root / "opencode.json",
            ),
            sources,
        )
    paths = tuple(path for path in (base_path, overlay_path) if path is not None)
    layers = tuple(_parse_config(path, sources.read_text(path)) for path in paths)
    selected = overlay_path or base_path
    return OmoConfigDiscovery(selected, layers)


def resolve_stale_timeout(
    discovery: OmoConfigDiscovery | ParsedOmoConfig | None,
) -> ResolvedStaleTimeout:
    """Resolve the highest-priority explicit value or OmO's documented 3-minute default."""
    match discovery:
        case OmoConfigDiscovery(config_path=config_path, layers=layers):
            pass
        case ParsedOmoConfig(path=path) as config:
            config_path = path
            layers = (config,)
        case None:
            config_path = None
            layers = ()
        case unreachable:
            assert_never(unreachable)
    for config in reversed(layers):
        if config.stale_timeout_ms is not None:
            return ResolvedStaleTimeout(
                config.stale_timeout_ms,
                ConfigValueSource.CONFIG,
                config_path,
                True,
                config.path,
            )
    return ResolvedStaleTimeout(
        DEFAULT_STALE_TIMEOUT_MS,
        ConfigValueSource.DEFAULT,
        config_path,
        bool(layers),
    )


def strip_jsonc_line_comments(raw: str) -> str:
    """Remove JSONC comments while preserving comment markers inside strings."""
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(raw):
        character = raw[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if character == "/" and index + 1 < len(raw) and raw[index + 1] == "/":
            newline = raw.find("\n", index + 2)
            if newline < 0:
                break
            output.append("\n")
            index = newline + 1
            continue
        if character == "/" and index + 1 < len(raw) and raw[index + 1] == "*":
            closing = raw.find("*/", index + 2)
            if closing < 0:
                break
            index = closing + 2
            continue
        output.append(character)
        index += 1
    return "".join(output)


def _first_existing(candidates: tuple[Path, ...], io: OmoConfigIO) -> Path | None:
    return next((path for path in candidates if io.path_exists(path)), None)


def _parse_config(path: Path, raw: str) -> ParsedOmoConfig:
    return parse_omo_config(path, raw)


def parse_omo_config(path: Path, raw: str) -> ParsedOmoConfig:
    """Parse the read-only policy subset from JSON or JSONC text."""
    data = json.loads(_strip_trailing_commas(strip_jsonc_line_comments(raw)))
    if not isinstance(data, dict):
        return ParsedOmoConfig(path, False, None)
    background_task = data.get("background_task")
    if not isinstance(background_task, dict):
        return ParsedOmoConfig(path, False, None)
    timeout = background_task.get("staleTimeoutMs")
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        return ParsedOmoConfig(path, True, None)
    return ParsedOmoConfig(path, True, timeout)


def _strip_trailing_commas(raw: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(raw):
        character = raw[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
        if character == ",":
            next_index = index + 1
            while next_index < len(raw) and raw[next_index].isspace():
                next_index += 1
            if next_index < len(raw) and raw[next_index] in "}]":
                index += 1
                continue
        output.append(character)
        index += 1
    return "".join(output)
