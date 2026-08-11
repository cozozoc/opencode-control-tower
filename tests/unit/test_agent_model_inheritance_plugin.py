from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import TypeAlias

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_PATH = REPOSITORY_ROOT / "plugins" / "inherit-parent-model.js"
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def _apply_plugin(config: JsonObject) -> JsonObject:
    node_program = """
const source = require("node:fs").readFileSync(process.argv[1], "utf8");
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
import(moduleUrl).then(async ({ default: plugin }) => {
  const config = JSON.parse(process.argv[2]);
  const hooks = await plugin({});
  hooks.config(config);
  process.stdout.write(JSON.stringify(config));
});
"""
    completed = subprocess.run(
        ["node", "-e", node_program, str(PLUGIN_PATH), json.dumps(config)],
        check=True,
        capture_output=True,
        text=True,
    )
    result: JsonObject = json.loads(completed.stdout)
    assert isinstance(result, dict)
    return result


def test_config_hook_removes_only_agent_model_overrides() -> None:
    config: JsonObject = {
        "model": "provider/parent",
        "small_model": "provider/small",
        "variant": "high",
        "permission": {"edit": "deny"},
        "agent": {
            "explore": {
                "model": "provider/child-a",
                "variant": "low",
                "prompt": "keep-a",
                "tools": {"read": True},
                "permission": {"bash": "deny"},
            },
            "general": {
                "model": "provider/child-b",
                "description": "keep-b",
                "mode": "subagent",
            },
        },
    }

    result = _apply_plugin(config)

    assert result == {
        "model": "provider/parent",
        "small_model": "provider/small",
        "variant": "high",
        "permission": {"edit": "deny"},
        "agent": {
            "explore": {
                "variant": "low",
                "prompt": "keep-a",
                "tools": {"read": True},
                "permission": {"bash": "deny"},
            },
            "general": {
                "description": "keep-b",
                "mode": "subagent",
            },
        },
    }


@pytest.mark.parametrize("agent", [None, {}])
def test_config_hook_accepts_missing_or_empty_agent(agent: JsonObject | None) -> None:
    config: JsonObject = {"model": "provider/parent"}
    if agent is not None:
        config["agent"] = agent

    result = _apply_plugin(config)

    assert result == config
