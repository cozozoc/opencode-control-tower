from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY_ROOT / "install.sh"
PLUGIN_SOURCE = REPOSITORY_ROOT / "plugins" / "inherit-parent-model.js"


def _shell_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    drive = path.drive.removesuffix(":").lower()
    suffix = path.as_posix().split(":", maxsplit=1)[1]
    return f"/mnt/{drive}{suffix}"


def _sandbox(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    commands = tmp_path / "commands"
    home.mkdir()
    commands.mkdir()
    stubs = {
        "python3": """#!/bin/bash
if [ "${1:-}" = "--version" ]; then
  echo "Python 3.11.9"
  exit 0
fi
exec /usr/bin/python3 "$@"
""",
        "pip": "#!/bin/bash\nexit 0\n",
        "tmux": "#!/bin/bash\nexit 0\n",
        "opencode": "#!/bin/bash\nexit 0\n",
    }
    for name, content in stubs.items():
        stub = commands / name
        stub.write_text(content, encoding="utf-8", newline="\n")
        stub.chmod(0o755)
    return home, commands


def _run_installer(home: Path, commands: Path) -> subprocess.CompletedProcess[str]:
    environment = (
        f"HOME={shlex.quote(_shell_path(home))} "
        f"PATH={shlex.quote(_shell_path(commands))}:/usr/bin:/bin"
    )
    invocation = f"{environment} bash {shlex.quote(_shell_path(INSTALLER))}"
    command = ["bash", "-lc", invocation] if os.name == "nt" else ["bash", "-c", invocation]
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_installer_deploys_plugin_and_fallback_in_sandbox(tmp_path: Path) -> None:
    home, commands = _sandbox(tmp_path)

    completed = _run_installer(home, commands)

    deployed = home / ".config/opencode/plugins/inherit-parent-model.js"
    assert deployed.read_text(encoding="utf-8") == PLUGIN_SOURCE.read_text(encoding="utf-8")
    assert (home / ".config/opencode/opencode-fallback.jsonc").is_file()
    assert "opencode-runtime-fallback" in (
        home / ".config/opencode/opencode.jsonc"
    ).read_text(encoding="utf-8")
    assert "RESTART REQUIRED" in completed.stdout


def test_installer_refreshes_plugin_without_changing_existing_config(tmp_path: Path) -> None:
    home, commands = _sandbox(tmp_path)
    config_dir = home / ".config/opencode"
    plugin_dir = config_dir / "plugins"
    plugin_dir.mkdir(parents=True)
    deployed = plugin_dir / "inherit-parent-model.js"
    deployed.write_text("stale plugin\n", encoding="utf-8")
    config = config_dir / "opencode.jsonc"
    original = """{
  "model": "provider/parent",
  "small_model": "provider/small",
  "agent": {"custom": {"model": "provider/explicit", "variant": "high"}}
}
"""
    config.write_text(original, encoding="utf-8")

    _run_installer(home, commands)

    assert deployed.read_text(encoding="utf-8") == PLUGIN_SOURCE.read_text(encoding="utf-8")
    assert json.loads(config.read_text(encoding="utf-8")) == {
        "model": "provider/parent",
        "small_model": "provider/small",
        "plugin": ["opencode-runtime-fallback"],
        "agent": {
            "custom": {"model": "provider/explicit", "variant": "high"},
        },
    }


def test_installer_is_idempotent_in_sandbox(tmp_path: Path) -> None:
    home, commands = _sandbox(tmp_path)
    first = _run_installer(home, commands)
    tracked = [
        home / ".tmux.conf",
        home / ".bashrc",
        home / ".config/opencode/opencode.jsonc",
        home / ".config/opencode/opencode-fallback.jsonc",
        home / ".config/opencode/plugins/inherit-parent-model.js",
    ]
    first_contents = {path: path.read_bytes() for path in tracked}

    second = _run_installer(home, commands)

    assert {path: path.read_bytes() for path in tracked} == first_contents
    assert "RESTART REQUIRED" in first.stdout
    assert "RESTART REQUIRED" in second.stdout
