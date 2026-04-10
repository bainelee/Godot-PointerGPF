# Godot Adapter Contract v1

## Purpose

This contract defines the minimum integration requirements for using PointerGPF MCP in arbitrary Godot projects.

## Transport Modes

- `plugin_adapter`: Godot plugin exposes adapter capability directly.
- `file_bridge`: file-based command/response bridge.

## Runtime Bridge (`file_bridge`)

Project-relative paths (same as `runtime_bridge` in `mcp/adapter_contract_v1.json`):

- **Command file**: `pointer_gpf/tmp/command.json` — MCP `run_game_basic_test_flow` writes one JSON object per step; the runtime adapter must read, act, then delete or replace as specified by your integration (the packaged plugin removes the command file after handling).
- **Response file**: `pointer_gpf/tmp/response.json` — adapter writes a JSON object that matches the current `seq` and `run_id` from the command. Minimum fields: `ok` (bool), `seq` (int), `run_id` (string). Additional action-specific fields (`message`, `elapsedMs`, `details`, etc.) follow the required/optional action contracts above.
- **Stop-Play flag file** (editor + `file_bridge` integration): `pointer_gpf/tmp/auto_stop_play_mode.flag` — written by the runtime bridge when handling `closeProject` so the **editor** plugin can stop Play without quitting the editor. Payload must carry `issued_at_unix` (Unix time in seconds) for freshness; the editor plugin ignores stale or malformed flags so leftover files do not terminate a user’s manual Play session. See `runtime_bridge.auto_stop_play_mode_flag_*` in `mcp/adapter_contract_v1.json`.

### 编辑器未启动时的引导顺序（MCP + EditorPlugin）

1. **MCP** 在尝试进入 Play 门闩前，写入 `pointer_gpf/tmp/mcp_bootstrap_session.json`（UTF-8 JSON 对象），至少包含：
   - `session_id`（字符串，UUID）
   - `issued_at_unix`（数字，秒级 Unix 时间，由 MCP 写入）
2. 若未检测到已打开的 Godot 编辑器进程持有该 `project_root`（MCP 侧 `_is_godot_editor_running_for_project`），MCP 使用已配置的 Godot 可执行文件路径执行 `Godot --editor --path <project_root>`（`_launch_godot_editor`）。
3. **EditorPlugin** 在编辑器已打开该工程且插件启用后，于常规门闩刷新路径中读取上述文件；若存在且 `session_id` 非空，则在写入 `pointer_gpf/tmp/runtime_gate.json` 时附带字段 **`bootstrap_session_ack`**，其值**等于**当前文件中的 `session_id`。
4. **MCP** 轮询 `runtime_gate.json`，直到 `bootstrap_session_ack == session_id` 或超时；该条件成立表示「该工程实例上的 PointerGPF 编辑器插件已加载并具备写门闩能力」，即本仓库所称的**工程加载完成（GPF 视角）**。
5. 随后 MCP 写入 `auto_enter_play_mode.flag` 并继续等待 `runtime_gate_passed == true`（现有 Play 门闩），再执行流程步骤。

**装载 GPF 的 IDE 义务（非 Godot 内代码）：** 允许 MCP 进程以分离子进程方式启动 Godot；在无法通过 `tools/game-test-runner/config/godot_executable.json`、工具参数或 `GODOT_*` 环境变量解析到可执行文件时，由集成方在调用 `run_game_basic_test_flow*` 时传入 `godot_executable`（或等价别名字段），而不是要求终端用户手动点击启动编辑器。

### `TIMEOUT` semantics

If the MCP runner does not observe a **valid** response (matching `seq` and `run_id`, parseable JSON, `seq` coercible to int) within `step_timeout_ms`, the tool fails with error code **`TIMEOUT`** and returns an `execution_report` with partial **phase coverage** (for example `started` without `result`). This is **not** the same as an in-step `wait` action timing out inside the game: the latter is decided by the adapter when executing that step.

## Required Actions

- `launchGame`
- `click`
- `wait`
- `check`
- `snapshot`
- `closeProject` (must **request ending the Play running state** for the current test run — same class of action as the editor **Stop** button via the bridge below; **do not** read this as “quit the Godot editor application / OS process”)

Each required action must return a structured response with:

- `ok` (bool)
- action-specific fields
- `message` or `details` for diagnostics

`closeProject` must request **stopping Play mode** and returning the editor to an idle editing state (default: **do not** exit the Godot editor process). In the packaged `file_bridge` reference implementation, the runtime bridge writes `pointer_gpf/tmp/auto_stop_play_mode.flag`; the **EditorPlugin** consumes that file and calls `EditorInterface.stop_playing_scene()`. If the flag file cannot be written, the bridge must return `ok=false` with error code **`STOP_FLAG_WRITE_FAILED`** (not a success response).

## Teardown semantics (`closeProject`)

- **What `closeProject` does:** it requests an end to the **Play running state** by having the runtime bridge write `pointer_gpf/tmp/auto_stop_play_mode.flag`; the **EditorPlugin** polls that flag and, when valid, calls **`EditorInterface.stop_playing_scene()`** — the same capability family as clicking **Stop** in the editor toolbar. It does **not** shut down the Godot editor executable unless your integration chooses a separate quit path.
- **“Keep editor” / default “do not exit Godot”:** this means the **editor application process** (the IDE) typically **remains running**. It does **not** mean leaving **Play** running or skipping `stop_playing_scene()`.
- **Recommended “teardown complete” checks for integrators:** (1) the file-bridge **`closeProject` response** is `ok` with matching `seq` / `run_id`; **and** (2) after a short poll of `pointer_gpf/tmp/runtime_gate.json` (written by the packaged plugin, e.g. `_write_runtime_gate_marker` / `_sync_runtime_gate_marker` in `plugin.gd`), the marker reflects a non-Play idle editor — typically **`runtime_mode`** is not `play_mode` (e.g. `editor_bridge`) and **`runtime_gate_passed`** is `false`, consistent with `EditorInterface.is_playing_scene()` being false once the plugin refreshes the gate. The bridge may acknowledge before the next gate write; polling covers that window.
- **`execution_report` vs `project_close` (MCP tools):** On failure or timeout, `execution_report.runtime_mode` / `runtime_gate_passed` are the **in-flow snapshot** when the runner stopped (often still `play_mode` / `true`). They are **not** updated after `closeProject`. **`project_close.play_running_by_runtime_gate`** and **`runtime_gate_snapshot_*`** reflect **`runtime_gate.json` after** teardown. If both disagree, MCP sets **`project_close.stale_execution_report_runtime_fields`** and **`stale_execution_report_note`** so agents do not treat `execution_report` as proof that Play is still running. **`runtime_gate_snapshot_immediate`** is read **after** the bridge ack for `closeProject`; the editor may already have stopped Play, so it may already show `editor_bridge` even though `execution_report` still says `play_mode`.

## Optional Actions

- `moveMouse`
- `drag`
- `inputText`
- `openMenu`
- `loadSlot`
- `saveSlot`
- `getState`
- `checkVisualHard`
- `captureUiSnapshot`

## `check.kind=visual_hard` Recommendation

For Figma collaboration scenarios, when a step uses `check` with `kind=visual_hard`, adapter should return `details` with at least:

- `status`
- `artifactPath`
- `resolution`
- `message`

This allows MCP-side tools to align Figma baseline data with runtime evidence.

## Error Model

Adapter should return stable, machine-readable error codes:

- `INVALID_ARGUMENT`
- `TARGET_NOT_FOUND`
- `ACTION_NOT_SUPPORTED`
- `NOT_IN_PLAY_MODE`
- `INPUT_PATH_BLOCKED`
- `TIMEOUT`
- `ENGINE_RUNTIME_STALLED`
- `ENGINE_DIAGNOSTICS_FATAL`
- `RUNTIME_EXCEPTION`
- `IO_ERROR`
- `STOP_FLAG_WRITE_FAILED` — `closeProject` could not write `auto_stop_play_mode.flag` (disk/permissions/locking).

## Runtime/Input Requirements

For runtime input contract compliance, adapter/runtime execution should provide:

- `runtime_mode_required`: `play_mode`
- `runtime_entry_allowed`: `f5_equivalent` | `already_running_play_session` | `unknown`
- `input_mode`: `in_engine_virtual_input`
- `os_input_interference`: `false`
- `protocol_mode`: `three_phase`
- `fail_fast_on_verify`: `true`

## Chat Protocol Compatibility

Seed flows and stepwise output assume three-phase chat compatibility:

- `started`
- `result`
- `verify`

## Machine-Readable Source

The authoritative JSON version is:

- `mcp/adapter_contract_v1.json`
