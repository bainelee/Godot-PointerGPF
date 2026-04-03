# Godot Adapter Contract v1

## Purpose

This contract defines the minimum integration requirements for using PointerGPF MCP in arbitrary Godot projects.

## Transport Modes

- `plugin_adapter`: Godot plugin exposes adapter capability directly.
- `file_bridge`: file-based command/response bridge.

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
