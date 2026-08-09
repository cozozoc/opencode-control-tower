"""One-command launch: start octower, detect port, auto-open attach terminal."""
import os, re, shutil, subprocess, sys, time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
USER_CWD = Path.cwd().resolve()
SRC = str(PROJECT / "src")
os.environ["PYTHONPATH"] = SRC
sys.path.insert(0, SRC)

env = {**os.environ, "PYTHONUNBUFFERED": "1"}

print(">>> Starting Control Tower...", flush=True)
proc = subprocess.Popen(
    [sys.executable, "-u", "-m", "octower", "--fast", "--project", str(USER_CWD)],
    cwd=PROJECT,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    env=env,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)

opencode_exe = r"C:\Users\thomas\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe"
port: str | None = None
healthy = False

try:
    for line in proc.stdout:
        print(line, end="", flush=True)
        if healthy:
            continue
        m = re.search(r"Server starting on http://127\.0\.0\.1:(\d+)", line)
        if m:
            port = m.group(1)
        if port and "state=healthy" in line:
            print(f"\n>>> Opening attach on port {port}...", flush=True)
            name = USER_CWD.name
            tab_title = name if len(name) <= 25 else name[:24] + "…"
            ps_cmd = f"& '{opencode_exe}' attach http://127.0.0.1:{port}"
            subprocess.Popen(
                ["wt", "-w", "0", "new-tab", "--title", tab_title, "--suppressApplicationTitle",
                 "powershell", "-NoExit", "-Command", ps_cmd],
                cwd=PROJECT,
                env={**os.environ, "WT_SESSION": os.environ.get("WT_SESSION", "")},
            )
            healthy = True
except KeyboardInterrupt:
    print("\n>>> Shutting down...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

print(">>> Done.")
