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

### `TIMEOUT` semantics

If the MCP runner does not observe a **valid** response (matching `seq` and `run_id`, parseable JSON, `seq` coercible to int) within `step_timeout_ms`, the tool fails with error code **`TIMEOUT`** and returns an `execution_report` with partial **phase coverage** (for example `started` without `result`). This is **not** the same as an in-step `wait` action timing out inside the game: the latter is decided by the adapter when executing that step.

## Required Actions

- `launchGame`
- `click`
- `wait`
- `check`
- `snapshot`

Each required action must return a structured response with:

- `ok` (bool)
- action-specific fields
- `message` or `details` for diagnostics

## Optional Actions

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
- `TIMEOUT`
- `RUNTIME_EXCEPTION`
- `IO_ERROR`

## Chat Protocol Compatibility

Seed flows and stepwise output assume three-phase chat compatibility:

- `started`
- `result`
- `verify`

## Machine-Readable Source

The authoritative JSON version is:

- `mcp/adapter_contract_v1.json`
