# V2 Plugin And Runtime Map

## Source Of Truth In This Repository

The V2 Godot plugin source lives in this repository under:

- [plugin.cfg](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/plugin.cfg)
- [plugin.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/plugin.gd)
- [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd)
- [runtime_diagnostics_logger.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_diagnostics_logger.gd)
- [runtime_diagnostics_writer.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_diagnostics_writer.gd)

The sync logic is implemented in:

- [plugin_sync.py](/D:/AI/pointer_gpf/v2/mcp_core/plugin_sync.py)

## What Gets Synced Into A Target Godot Project

When V2 runs `sync_godot_plugin`, these plugin files are copied into the target project here:

- `目标工程/addons/pointer_gpf/plugin.cfg`
- `目标工程/addons/pointer_gpf/plugin.gd`
- `目标工程/addons/pointer_gpf/runtime_bridge.gd`
- `目标工程/addons/pointer_gpf/runtime_diagnostics_logger.gd`
- `目标工程/addons/pointer_gpf/runtime_diagnostics_writer.gd`

The same sync step also rewrites `project.godot` so that:

- `[autoload]` contains `PointerGPFV2RuntimeBridge="*res://addons/pointer_gpf/runtime_bridge.gd"`
- `[editor_plugins]` enables `res://addons/pointer_gpf/plugin.cfg`
- old legacy bridge autoload entries are removed
- a `uid://...` main scene reference is conservatively resolved to a concrete `res://...` path when possible

## Runtime Files Created Inside The Target Project

At runtime, the plugin writes and reads project-local files under:

- `目标工程/pointer_gpf/tmp/`

Important files:

- `runtime_gate.json`
  - written by `plugin.gd`
  - tells V2 whether Godot editor play mode is currently active
- `command.json`
  - written by the Python V2 runner
  - contains the next action for the bridge to execute
- `response.json`
  - written by `runtime_bridge.gd`
  - contains the bridge response for the current step
- `runtime_diagnostics.json`
  - written by `runtime_diagnostics_writer.gd`
  - contains recent bridge errors and runtime engine errors
- `runtime_session.json`
  - written by `runtime_bridge.gd`
  - identifies the runtime process under test for `isolated_runtime`
- `auto_enter_play_mode.flag`
  - written by the Python side when it wants the editor plugin to enter play mode
- `auto_stop_play_mode.flag`
  - written by the bridge when `closeProject` asks the editor plugin to stop play mode

`run_basic_flow` now also syncs the repository plugin source into the target project before preflight and launch, so runtime mode changes in this repository are applied to the next flow run without requiring a separate manual `sync_godot_plugin` step.

## File Responsibilities

### `plugin.gd`

Runs as an editor plugin. It is responsible for:

- polling the editor play-mode state
- keeping `runtime_gate.json` in sync
- honoring `auto_enter_play_mode.flag`
- honoring `auto_stop_play_mode.flag`

It does not execute flow actions itself.

### `runtime_bridge.gd`

Runs as the autoload bridge inside the target project runtime. It is responsible for:

- polling `command.json`
- deduplicating commands by `run_id` and `seq`
- dispatching `launchGame`, `click`, `wait`, `check`, `snapshot`, `closeProject`
- writing `response.json`
- requesting play-mode stop for `closeProject`
- writing `runtime_session.json` so Python can verify the isolated runtime instance it launched
- applying runtime-side input guards that reduce captured-mouse symptoms during automation runs

Those input guards are a mitigation layer, not a complete isolation guarantee by themselves. The stronger isolation requirement is tracked separately in:

- [v2-input-isolation-requirements.md](/D:/AI/pointer_gpf/docs/v2-input-isolation-requirements.md)

### `runtime_diagnostics_logger.gd`

Hooks into Godot engine error logging and forwards runtime engine errors to the diagnostics writer.

### `runtime_diagnostics_writer.gd`

Aggregates bridge and engine-side runtime errors and periodically writes them into `runtime_diagnostics.json`.

## Important Operational Meaning

The plugin code is stored in this repository, but the plugin instance that actually runs is the synced copy inside the target Godot project.

So there are always two layers:

1. repository source:
   - `D:\AI\pointer_gpf\v2\godot_plugin\addons\pointer_gpf\...`
2. real runtime target:
   - `目标工程/addons/pointer_gpf/...`
   - `目标工程/pointer_gpf/tmp/...`

When debugging V2 behavior, always distinguish between:

- source plugin files in this repository
- synced plugin files inside the external Godot project
- runtime state files under `目标工程/pointer_gpf/tmp/`

Tool payload note:

- `run_basic_flow` result payloads now include an `isolation` object
- `play_mode` runs report `isolation.status: shared_desktop`
- `isolated_runtime` runs report `isolation.status: isolated_desktop`
- `isolated_runtime` runs also report `host_desktop_name` and `separate_desktop`
