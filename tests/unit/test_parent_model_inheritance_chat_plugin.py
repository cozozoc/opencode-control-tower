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


def _apply_chat_message(scenario: JsonObject) -> JsonObject:
    node_program = """
const source = require("node:fs").readFileSync(process.argv[1], "utf8");
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
import(moduleUrl).then(async ({ default: plugin }) => {
  const scenario = JSON.parse(process.argv[2]);
  const calls = { get: [], messages: [] };
  const client = {
    session: {
      get: async (request) => {
        calls.get.push(request);
        if (scenario.sessionReject) throw new Error("session rejected");
        return scenario.session;
      },
      messages: async (request) => {
        calls.messages.push(request);
        if (scenario.messagesReject) throw new Error("messages rejected");
        return scenario.messages;
      },
    },
  };
  const hooks = await plugin({ client });
  const output = scenario.output;
  await hooks["chat.message"]({ sessionID: scenario.sessionID }, output);
  process.stdout.write(JSON.stringify({ output, calls }));
});
"""
    completed = subprocess.run(
        ["node", "-e", node_program, str(PLUGIN_PATH), json.dumps(scenario)],
        check=True,
        capture_output=True,
        text=True,
    )
    result: JsonObject = json.loads(completed.stdout)
    assert isinstance(result, dict)
    return result


def test_chat_message_overrides_explicit_child_model_with_latest_parent_user_model() -> None:
    result = _apply_chat_message(
        {
            "sessionID": "child",
            "session": {"data": {"id": "child", "parentID": "parent"}},
            "messages": {
                "data": [
                    {
                        "info": {
                            "role": "user",
                            "model": {"providerID": "provider", "modelID": "older"},
                            "variant": "low",
                        },
                    },
                    {"info": {"role": "assistant"}},
                    {
                        "info": {
                            "role": "user",
                            "model": {"providerID": "provider", "modelID": "latest"},
                            "variant": "high",
                        },
                    },
                ],
            },
            "output": {
                "message": {
                    "model": {"providerID": "omo", "modelID": "explicit"},
                    "variant": "low",
                    "agent": "category-agent",
                },
            },
        }
    )

    assert result["output"] == {
        "message": {
            "model": {
                "providerID": "provider",
                "modelID": "latest",
                "variant": "high",
            },
            "agent": "category-agent",
        },
    }


def test_chat_message_accepts_unwrapped_sdk_responses() -> None:
    result = _apply_chat_message(
        {
            "sessionID": "child",
            "session": {"id": "child", "parentID": "parent"},
            "messages": [
                {
                    "info": {
                        "role": "user",
                        "model": {"providerID": "provider", "modelID": "parent"},
                    },
                },
            ],
            "output": {
                "message": {"model": {"providerID": "omo", "modelID": "explicit"}},
            },
        }
    )

    assert result["output"] == {
        "message": {"model": {"providerID": "provider", "modelID": "parent"}},
    }


def test_chat_message_leaves_root_session_unchanged() -> None:
    output: JsonObject = {
        "message": {"model": {"providerID": "provider", "modelID": "root"}},
    }
    result = _apply_chat_message(
        {
            "sessionID": "root",
            "session": {"data": {"id": "root"}},
            "messages": {"data": []},
            "output": output,
        }
    )

    assert result["output"] == output
    assert result["calls"] == {
        "get": [{"path": {"id": "root"}}],
        "messages": [],
    }


def test_chat_message_removes_explicit_child_variant_when_parent_has_none() -> None:
    result = _apply_chat_message(
        {
            "sessionID": "child",
            "session": {"data": {"parentID": "parent"}},
            "messages": {
                "data": [
                    {
                        "info": {
                            "role": "user",
                            "model": {"providerID": "provider", "modelID": "parent"},
                        },
                    },
                ],
            },
            "output": {
                "message": {
                    "model": {"providerID": "omo", "modelID": "explicit"},
                    "variant": "low",
                },
            },
        }
    )

    assert result["output"] == {
        "message": {"model": {"providerID": "provider", "modelID": "parent"}},
    }


@pytest.mark.parametrize(
    "scenario",
    [
        {"session": {"data": None}, "messages": {"data": []}},
        {"session": {"data": {"parentID": "parent"}}, "messages": {"data": []}},
        {
            "session": {"data": {"parentID": "parent"}},
            "messages": {"data": [{"info": {"role": "user", "model": {}}}]},
        },
        {
            "session": {"data": {"parentID": "parent"}},
            "messages": {
                "data": [
                    {
                        "info": {
                            "role": "user",
                            "model": {"providerID": "", "modelID": ""},
                        },
                    },
                ],
            },
        },
        {"sessionReject": True},
        {"session": {"data": {"parentID": "parent"}}, "messagesReject": True},
    ],
)
def test_chat_message_leaves_model_unchanged_for_invalid_sdk_results(
    scenario: JsonObject,
) -> None:
    output: JsonObject = {
        "message": {"model": {"providerID": "omo", "modelID": "explicit"}},
    }
    scenario.update({"sessionID": "child", "output": output})

    result = _apply_chat_message(scenario)

    assert result["output"] == output
