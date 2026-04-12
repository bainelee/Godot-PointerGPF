# V2 Handoff

## Read First

When continuing V2 work in a new conversation, read these files first:

1. [v2-status.md](/D:/AI/pointer_gpf/docs/v2-status.md)
2. [v2-architecture.md](/D:/AI/pointer_gpf/docs/v2-architecture.md)
3. [v2-basic-flow-user-intent.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-user-intent.md)
4. [v2-basic-flow-contract.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-contract.md)
5. [v2-basic-flow-asset-model.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-asset-model.md)
6. [v2-basic-flow-staleness-and-generation.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-staleness-and-generation.md)
7. [v2-plugin-runtime-map.md](/D:/AI/pointer_gpf/docs/v2-plugin-runtime-map.md)
8. [godot-resource-uid-drift-and-false-mcp-failures.md](/D:/AI/pointer_gpf/docs/godot-resource-uid-drift-and-false-mcp-failures.md)

## Current Repository Shape

`main` is now intentionally V2-only.

Current top-level tracked shape is:

- `.cursor`
- `.github`
- `docs`
- `scripts`
- `v2`
- root metadata files such as `README.md`, `README.zh-CN.md`, `AGENTS.md`, `LICENSE`

The old MCP system is no longer present on `main`.
Use `legacy/mcp` only when historical reference is required.

## Current State

V2 phase 1 minimal chain is already passing.

Verified:

- V2 preflight passes on `D:\AI\pointer_gpf_testgame`
- V2 minimal flow passes on `D:\AI\pointer_gpf_testgame`
- V2 interactive flow passes on `D:\AI\pointer_gpf_testgame`
- V2 `generate_basic_flow` writes `basicflow.json` + `basicflow.meta.json`
- V2 default `run_basic_flow` passes against project-local `basicflow.json` after plugin sync and clean restart
- V2 can run a stale project-local `basicflow` when `--allow-stale-basicflow` is explicitly provided
- V2 can analyze why the current project-local `basicflow` is stale through `analyze_basic_flow_staleness`
- V2 `generate_basic_flow` accepts either `--answers-file` or direct structured answers for the 3 generation questions
- V2 `get_basic_flow_generation_questions` returns the structured 3-question contract plus the current startup-scene hint
- V2 also supports a session form for the 3-question generation flow: start -> answer -> complete
- V2 generated `basicflow` can now conservatively switch to a project-specific path when obvious targets are detected
- V2 validated a real project-specific path on `D:\AI\pointer_gpf_testgame`: `StartButton -> GameLevel -> GamePointerHud -> closeProject`
- V2 project-specific target inference is no longer limited to that exact path; it can now conservatively infer:
  - `button_to_scene_with_runtime_anchor`
  - `button_to_scene_root`
  - fallback `generic_runtime_probe`
- `run_basic_flow` now syncs the repository plugin into the target project before preflight and launch
- V2 has an experimental Windows `isolated_runtime` mode for `run_basic_flow`
- `run_basic_flow` now returns an `isolation` object so callers can distinguish shared desktop vs isolated desktop execution
- isolated-runtime payloads now also include `host_desktop_name` and `separate_desktop`
- V2 fixed regression now passes with `Ran 66 tests`, `OK`
- V2 rejects overlapping flow runs for one project with `FLOW_ALREADY_RUNNING`
- V2 rejects manual multi-editor runs for one project with `MULTIPLE_EDITOR_PROCESSES_DETECTED`
- user language like `跑基础测试流程` should be interpreted as `run_basic_flow`

## Current Verification Commands

Run these first in a new session:

Run flow commands serially against `D:\AI\pointer_gpf_testgame`. Do not overlap two flow runs against the same shared `pointer_gpf/tmp`.

Preferred fixed regression entry:

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame
```

Optional isolated-runtime coverage:

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame --include-isolated-runtime
```

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame --include-isolated-runtime --include-host-activity
```

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-isolated-runtime.py --project-root D:\AI\pointer_gpf_testgame
```

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-isolated-runtime-with-host-activity.py --project-root D:\AI\pointer_gpf_testgame
```

Current fixed regression coverage includes:

- V2 unit tests
- `preflight_project`
- `basic_interactive_flow`
- `get_basic_flow_generation_questions`
- session-based `basicflow` generation
- default project-local `run_basic_flow`
- `analyze_basic_flow_staleness`
- stale override `run_basic_flow --allow-stale-basicflow`
- runtime guard checks
- optional isolated runtime minimal + interactive flows

```powershell
python -m v2.mcp_core.server --tool generate_basic_flow --project-root D:\AI\pointer_gpf_testgame --answers-file D:\AI\pointer_gpf\pointer_gpf\tmp\basicflow_answers.json
```

```powershell
python -m v2.mcp_core.server --tool generate_basic_flow --project-root D:\AI\pointer_gpf_testgame --main-scene-is-entry true --tested-features "进入主流程,基础操作" --include-screenshot-evidence false
```

```powershell
python -m v2.mcp_core.server --tool get_basic_flow_generation_questions --project-root D:\AI\pointer_gpf_testgame
```

```powershell
python -m v2.mcp_core.server --tool start_basic_flow_generation_session --project-root D:\AI\pointer_gpf_testgame
python -m v2.mcp_core.server --tool answer_basic_flow_generation_session --project-root D:\AI\pointer_gpf_testgame --session-id <id> --question-id main_scene_is_entry --answer true
python -m v2.mcp_core.server --tool answer_basic_flow_generation_session --project-root D:\AI\pointer_gpf_testgame --session-id <id> --question-id tested_features --answer "进入主流程,基础操作"
python -m v2.mcp_core.server --tool answer_basic_flow_generation_session --project-root D:\AI\pointer_gpf_testgame --session-id <id> --question-id include_screenshot_evidence --answer false
python -m v2.mcp_core.server --tool complete_basic_flow_generation_session --project-root D:\AI\pointer_gpf_testgame --session-id <id>
```

```powershell
python -m unittest D:\AI\pointer_gpf\v2\tests\test_preflight.py D:\AI\pointer_gpf\v2\tests\test_flow_runner.py D:\AI\pointer_gpf\v2\tests\test_plugin_sync.py D:\AI\pointer_gpf\v2\tests\test_server.py
```

```powershell
python -m v2.mcp_core.server --tool preflight_project --project-root D:\AI\pointer_gpf_testgame
```

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\basic_minimal_flow.json
```

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\basic_interactive_flow.json
```

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame
```

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --allow-stale-basicflow
```

```powershell
python -m v2.mcp_core.server --tool analyze_basic_flow_staleness --project-root D:\AI\pointer_gpf_testgame
```

Fixed regression expectation:

- if one flow is already running for `D:\AI\pointer_gpf_testgame`, the next flow returns `FLOW_ALREADY_RUNNING`
- if two Godot editors are open for `D:\AI\pointer_gpf_testgame`, `run_basic_flow` returns `MULTIPLE_EDITOR_PROCESSES_DETECTED`
- use `python D:\AI\pointer_gpf\scripts\verify-v2-runtime-guards.py --project-root D:\AI\pointer_gpf_testgame --check all` for a fixed runtime-guard regression without extra helper console windows

## Next Implementation Target

Continue with the `basicflow` productization work:

1. extend the conservative project-specific target inference beyond the currently validated `StartButton -> GameLevel -> GamePointerHud` path
2. keep regression coverage aligned when `basicflow` generation logic changes
3. preserve serial execution for flow runs and generation sessions against one shared project

Latest implementation note:

- inference now looks for a startup button scene, a scene-transition target from the startup script, the target scene root node, and an optional runtime anchor scene such as a HUD
- if those signals are missing, generation still falls back to the old generic visible-click probe
- input isolation is now an explicit architecture requirement; see [v2-input-isolation-requirements.md](/D:/AI/pointer_gpf/docs/v2-input-isolation-requirements.md)
- the current implementation plan for that work is [2026-04-12-v2-input-isolation-plan.md](/D:/AI/pointer_gpf/docs/2026-04-12-v2-input-isolation-plan.md)
- the first isolated-runtime slice is now implemented:
  - `run_basic_flow --execution-mode isolated_runtime` launches a Godot runtime onto a dedicated Windows desktop
  - `runtime_bridge.gd` writes `pointer_gpf/tmp/runtime_session.json`
  - `closeProject` quits the isolated runtime process directly instead of writing `auto_stop_play_mode.flag`
  - `project_close` is verified against the isolated runtime PID and stable stop window
  - result payloads now include `isolation.isolated`, `isolation.surface`, `isolation.status`, `host_desktop_name`, and `separate_desktop`
  - there is now a real host-desktop activity validation script that keeps moving the host cursor while isolated runtime flows run; the latest observed result still passed for both minimal and interactive flows
  - `runtime_bridge.gd` also adds automation-time input guards that reduce captured-mouse symptoms, but those guards should still be described as mitigation rather than as the full isolation proof

## Plugin Summary For Colleagues

The V2 Godot plugin source is stored under:

- [v2/godot_plugin/addons/pointer_gpf](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf)

It is synced into a target project as:

- `目标工程/addons/pointer_gpf/...`

The runtime state used by V2 is stored inside the target project as:

- `目标工程/pointer_gpf/tmp/runtime_gate.json`
- `目标工程/pointer_gpf/tmp/command.json`
- `目标工程/pointer_gpf/tmp/response.json`
- `目标工程/pointer_gpf/tmp/runtime_diagnostics.json`

Responsibility split:

- `plugin.gd`
  - editor-side play-mode gate sync and auto enter/stop handling
- `runtime_bridge.gd`
  - runtime-side command polling and flow action execution
- `runtime_diagnostics_logger.gd`
  - captures Godot engine errors
- `runtime_diagnostics_writer.gd`
  - writes aggregated runtime diagnostics to disk

## What Not To Do

Do not re-expand V2 with:

- auto-fix
- repair loop
- NL router
- Figma tools
- broad orchestration

Do not merge V2 back into the old huge `mcp/server.py` path.

## If V2 Appears Broken

Check in this order:

1. `project.godot`
   - V2 `[autoload]`
   - V2 `[editor_plugins]`
2. `pointer_gpf/tmp/runtime_gate.json`
3. `pointer_gpf/tmp/command.json`
4. `pointer_gpf/tmp/response.json`
5. `pointer_gpf/tmp/runtime_diagnostics.json`
6. external project resource UID consistency

## Prompt For New Conversation

Use this starter:

```text
继续 pointer_gpf 的 V2 工作。先读 docs/v2-status.md、docs/v2-architecture.md、docs/v2-plugin-runtime-map.md、docs/v2-handoff.md，然后按 AGENTS.md 要求先运行 python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame，复述关键输出，再继续做 basicflow 的项目特定目标推断扩展，并同步补测试与文档。
```
