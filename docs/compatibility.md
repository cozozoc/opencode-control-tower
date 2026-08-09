# OpenCode Background Agent Control Tower — Compatibility Report

> Phase 1 output (handoff §27 Phase 1 item 6).
> Verified against the **actually installed** versions on 2026-08-08 (Asia/Seoul).
> Handoff: `OPENCODE_BACKGROUND_AGENT_CONTROL_TOWER_V4_HANDOFF.md` (v4, frozen 2026-08-08).
> Status: authoritative for the environment where it was produced; re-verify after any
> OpenCode/OmO upgrade.

---

## 1. Environment matrix

| Component | Installed | Path / evidence |
|---|---|---|
| OS | Windows 11 (native execution) | — |
| WSL2 | Ubuntu (Stopped; tmux 3.x, Python 3.14.4 available) | `wsl -l -v` |
| OpenCode CLI | **1.18.15** | `opencode --version`; `C:\Users\thomas\AppData\Roaming\npm\node_modules\opencode-ai` |
| OpenCode SDK / Plugin | **@opencode-ai/sdk 1.18.15**, @opencode-ai/plugin 1.18.15 | `pccot-nsai-verification-harness\.opencode\node_modules` |
| OmO plugin | **oh-my-openagent 4.19.4** | `~\.cache\opencode\packages\oh-my-openagent@latest\node_modules\oh-my-openagent\package.json` |
| OmO config | `~/.omo/omo.jsonc` — **no `background_task` block** → schema defaults apply | file read |
| OpenCode config | `~/.config/opencode/opencode.jsonc` — plugins: `oh-my-openagent@latest`, `opencode-btw` | file read |
| Python (Guardian) | 3.11.6 (Windows), pytest 9.0.3 | `python --version` |

Notes:

- The handoff assumed WSL2 + tmux as the primary target. The currently installed setup runs
  OpenCode natively on Windows; WSL2 exists but is stopped. The v4 supervisor must therefore
  support **both** native-Windows and WSL2 launches (tmux stays optional for process containment).
- `~/.local/share/opencode/` (Windows: `C:\Users\thomas\.local\share\opencode\`) holds
  `opencode.db`, storage/, tool-output/, logs/ — matches handoff §2.7 persistence model.
- No server was running on port 4096 at verification time; the verification server was started
  and stopped by this Phase 1 run.

---

## 2. OpenCode API verification (live `opencode serve` + HTTP calls)

### 2.1 CLI support

| Handoff claim | Verified |
|---|---|
| `opencode serve [--port] [--hostname]` | ✅ 1.18.15; default `--hostname 127.0.0.1`, `--port` default 0 (docs say 4096 for standalone server; the flag default shown by help is `0`) |
| `opencode attach <url> [--session|-s] [--continue|-c] [--fork] [--dir] [--password/--username]` | ✅ all present; `OPENCODE_SERVER_PASSWORD` env supported |
| `--pure` (no external plugins) | ✅ available on both serve and attach |
| `--mdns` opt-in | ✅ present (default false, hostname stays localhost) — aligns with R12 |

### 2.2 Endpoints present in the installed `/doc` OpenAPI spec

All handoff §2.2 endpoints exist:

```text
GET  /global/health                  ✅ (returns {"healthy":true,"version":"1.18.15"})
GET  /global/event                   ✅
GET  /event                          ✅ SSE; verified live: "server.connected" event received
GET  /session                        ✅ (17 sessions listed)
GET  /session/status                 ⚠️ EXISTS BUT UNRELIABLE — see §2.4
GET  /session/{sessionID}            ✅
GET  /session/{sessionID}/children   ✅ (live: 2 children returned, parentID matched)
GET  /session/{sessionID}/todo       ✅ (live: returned [] for a session without todos)
GET  /session/{sessionID}/message    ✅ (live: 10 messages)
GET  /session/{sessionID}/message/{messageID} ✅
POST /session/{sessionID}/abort      ✅ (200 → boolean)
POST /session/{sessionID}/prompt_async ✅ (204 → void)
POST /session/{sessionID}/fork       ✅ (present; forbidden as normal recovery per INV-002)
```

Additional endpoints discovered (not in handoff §2.2):

```text
POST /experimental/session/{sessionID}/background
    → "Detach any synchronous subagents currently blocking the session and continue them
      in the background." (200 → boolean)
POST /experimental/control-plane/move-session
GET  /session/{sessionID}/init, /diff, /summarize, /command, /shell, /revert, /unrevert
GET  /session/{sessionID}/permissions/{permissionID}
GET  /tui/*  (append-prompt, submit-prompt, select-session, open-sessions, clear-prompt)
GET  /api/*  (legacy/alternate API surface: /api/session, /api/session/{id}/event,
              /api/session/{id}/interrupt, /api/session/{id}/wait, question/permission replies …)
```

Design impact: the `/api/*` family (session wait/interrupt/event, question+permission reply)
may provide a second, more stable control surface for the Guardian; not required for v4
baseline but worth a contract test in Phase 4.

### 2.3 SDK type facts (installed SDK 1.18.15, `dist/gen/types.gen.d.ts`)

| Type | Verified |
|---|---|
| `Session { id, projectID, directory, parentID?, summary?, time, modelID, providerID, mode, path }` | ✅ `parentID?: string` at types.gen.d.ts:469 — handoff §2.3 confirmed |
| `SessionStatus = {type:"idle"} \| {type:"retry", attempt, message, next} \| {type:"busy"}` | ✅ types.gen.d.ts:396-402 — handoff §2.4 confirmed |
| `Todo { content, status }` with status `pending/in_progress/completed/cancelled` | ✅ |
| Tool/part states `pending/running/completed/error` | ✅ (handoff §2.5) |
| `POST /session/{id}/abort` → `200: boolean` | ✅ |
| `POST /session/{id}/prompt_async` → `204: void` | ✅ (handoff §2.2 meanings confirmed) |

### 2.4 ⚠️ `/session/status` is NOT a durable status DB in 1.18.15 — CONFIRMED

Live call `GET /session/status` while 17 sessions existed returned an **empty object `{}`**
(all sessions were idle at that moment). The handoff §2.4 compatibility warning is therefore
**empirically confirmed on the installed version**: idle sessions are omitted; a stale `busy`
can also be expected.

**Design consequence (binding):**
- Guardian MUST NOT base DONE or STALL classification on `/session/status` alone (INV-007).
- Completion must use positive evidence (message/tool/todo/children) per handoff §10.
- A compatibility layer (`api/compatibility.py`) must treat `/session/status` as advisory
  enrichment only, and must pass integration tests against the installed server (Phase 4).

### 2.5 `/session/{id}/todo` semantics

Returned `[]` for a session that had never used todos. Confirms handoff §10:
"do not require TODO to exist" — absence of todo data must never block DONE classification.

---

## 3. OmO (oh-my-openagent) verification — 4.19.4

### 3.1 `staleTimeoutMs` conflict — REAL (handoff §3, Case M)

Installed 4.19.4 config schema (`dist/config/schema/background-task.d.ts`):

```text
staleTimeoutMs          default 180000 (3 min), min 60000   → "Interrupt tasks with no activity"
messageStalenessTimeoutMs default 1800000 (30 min), min 60000
taskTtlMs               default 1800000 (30 min), min 300000
sessionGoneTimeoutMs, taskCleanupDelayMs, syncPollTimeoutMs, maxToolCalls, circuitBreaker …
```

- `checkAndInterruptStaleTasks()` exists and interrupts stale tasks (task-poller).
- User `~/.omo/omo.jsonc` contains **no `background_task` block** → the **3-minute default is
  in effect**. This races Guardian's 5/10/15 policy exactly as the handoff predicted.
- Config path: unified `~/.omo/omo.jsonc` is correct for this install (legacy
  `oh-my-openagent.json[c]` not present).

**Required action (before auto-recovery is armed):**
`octower doctor` must report this conflict; Guardian must suggest
`"background_task": { "staleTimeoutMs": 1800000 }` and must not silently overwrite
(handoff §3, §21, §20).

### 3.2 OmO background mechanism — adapter facts

- OmO background tasks are **standard OpenCode sessions** created via the official SDK client
  (`PluginInput["client"]`); spawner uses `promptAsync`/`abort` (59 / 25 references in dist).
- **OmO does NOT call `/experimental/session/{id}/background`** (no reference in installed dist
  or upstream dev source). Do not build the OmO adapter around that endpoint.
- `~/.omo/run-continuation/` (`CONTINUATION_MARKER_DIR`) stores per-session, per-source
  continuation markers, e.g.:
  ```json
  {"sessionID":"ses_…","updatedAt":"…","sources":{"background-task":{"state":"idle","updatedAt":"…"}}}
  ```
  → usable as **additional completion/stall evidence** for the OmO adapter (handoff §7.3).
- OmO ships its own parent-wake machinery (`BACKGROUND_COMPLETION_WAKE_PENDING_REASON`,
  `parent-wake-*` modules), a `prompt-async-gate` (overlap guard ≈ INV-009) and a
  `stop-continuation-guard` hook. Guardian parent-wake (R10) must detect/avoid duplicating
  OmO's native wake.
- OmO has its own `todo-continuation-enforcer` + `opencode run` style completion tracking —
  do not fight it; treat as adapter evidence.

### 3.3 Split vs integrated mode — DECISION

Verified: OmO manages background work through the official SDK over the server API, not via
process/tmux-level interception. Therefore **split mode is compatible**:

```text
opencode serve --hostname 127.0.0.1 --port <port>
opencode attach http://127.0.0.1:<port> --session <root>
octower --url http://127.0.0.1:<port> --root <root>
```

Decision: **v4 default = split mode** (handoff §15 preferred). Integrated
`opencode --port <port>` remains a configurable fallback (`server.mode = "auto|split|integrated"`).
One caveat to re-check in Phase 6: OmO's tmux-pane background view may still be used as an
optional visual adapter, but it never affects the split-mode decision.

---

## 4. Verified facts that affect implementation (summary)

1. `/session/status` returns `{}` for idle sessions → never a stall/DONE source.
2. OmO default `staleTimeoutMs=180000` is live (no override in user config) → startup conflict
   warning mandatory before arming auto-recovery.
3. `parentID` is present on sessions and `/children` works → recursive discovery (R1) is
   feasible with `GET /session` + `parentID` tree assembly.
4. Todo absence is normal → completion must not depend on todos.
5. SSE `/event` works (`server.connected` observed) → event-first model (handoff §17) viable.
6. `prompt_async` returns 204 (accepted) — §13.4 "recovery success requires semantic activity,
   not HTTP 204" applies as documented.
7. OmO markers in `.omo/run-continuation/` are a real, file-based state source for adapter
   evidence (and a potential cross-check for Guardian's own journal location, which must not
   collide with OmO's marker dir; Guardian state stays in
   `~/.local/state/opencode-control-tower/` per handoff §13.1).

## 5. Known unknowns carried forward (handoff §30, updated)

- Exact `/session/status` behavior under mixed busy/idle load (needs Phase 4 contract tests
  with a live busy session).
- Whether OmO's `prompt-async-gate` blocks external `prompt_async` into a session OmO already
  owns (affects Guardian same-session resume through OmO-managed tasks — Phase 6).
- Internal Qwen provider overload signaling (HTTP codes / retry headers / streaming behavior)
  — requires the internal endpoint contract; until known, default protective behavior stands.
- Whether a long-running shell tool exposes per-step liveness in 1.18.15 messages/parts —
  Phase 4.
- Windows-native tmux substitute (e.g. optional `wt`/`conpty` layout) for non-WSL operation.
