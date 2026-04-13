# V2 Status

## Current Phase

V2 is in **phase 1.5**.

Current goal:

- keep the validated runtime chain stable
- start productizing `basicflow` as an explicit asset rather than a one-off runtime file
- define a real input-isolation path so flow execution does not depend on the user avoiding mouse/keyboard interaction on Windows
- avoid inheriting old system features such as auto-fix, NL routing, orchestration, and Figma workflows

## What Is Already Working

The following V2 capabilities are already implemented in `v2/`:

- `configure_godot_executable`
- `sync_godot_plugin`
- `preflight_project`
- `generate_basic_flow`
- `run_basic_flow`
- interactive flow actions: `click`, `wait`, `check`
- user request language such as `跑基础测试流程` maps to `run_basic_flow`
- project-local `basicflow.json` + `basicflow.meta.json`
- conservative `basicflow` stale detection
- `--allow-stale-basicflow` can run the old project-local `basicflow` after a stale warning decision
- `analyze_basic_flow_staleness` can explain why the current project-local `basicflow` may no longer match the project
- `generate_basic_flow` can now accept the 3 generation answers directly, without requiring `--answers-file`
- `get_basic_flow_generation_questions` returns the structured 3-question contract, including the current startup-scene hint
- `get_basic_flow_user_intents` returns a small structured intent catalog for the upper conversational layer
- `resolve_basic_flow_user_request` can map a small set of basicflow-related user phrases onto the project-aware next tool choice
- `plan_basic_flow_user_request` can map a basicflow-related user phrase onto an executable next tool call with args
- `plan_user_request` now exists as the top-level user-request planner entry, currently wired to `basicflow` and a small `project_readiness` slice
- `handle_user_request` now exists as a thin top-level user-request handler, currently auto-executing only safe next-step tools such as preflight, config, question collection, and staleness analysis
- V2 now also has an explicit user-facing command-boundary document: [v2-how-to-command-gpf.md](/D:/AI/pointer_gpf/docs/v2-how-to-command-gpf.md)
- `get_user_request_command_guide` now exposes the same bounded command set as a machine-readable payload for the upper layer
- V2 now also has an explicit development-side NL boundary rule set: [v2-natural-language-boundary-principles.md](/D:/AI/pointer_gpf/docs/v2-natural-language-boundary-principles.md)
- the planned post-slice refactor for oversized [server.py](/D:/AI/pointer_gpf/v2/mcp_core/server.py) is recorded in [2026-04-13-v2-server-split-plan.md](/D:/AI/pointer_gpf/docs/2026-04-13-v2-server-split-plan.md)
- both `basicflow` and `project_readiness` request phrases are now backed by shared in-code catalogs instead of ad hoc planner-only phrase lists
- V2 now has a minimal source-bundle release path plus a release smoke verifier; see [v2-release-and-install.md](/D:/AI/pointer_gpf/docs/v2-release-and-install.md)
- the 3-question generation flow also supports a session form: start -> answer -> complete
- generated `basicflow` can conservatively prefer a project-specific path when obvious targets are detected
- project-specific target inference now covers a broader button-to-scene pattern, not just one hard-coded testgame path
- `run_basic_flow` now syncs the latest repository plugin into the target project before preflight and launch
- experimental Windows `isolated_runtime` can launch the tested Godot runtime on a dedicated desktop and verify teardown against that runtime process

The current V2 structure lives under:

- [v2](/D:/AI/pointer_gpf/v2)

Key files:

- [server.py](/D:/AI/pointer_gpf/v2/mcp_core/server.py)
- [preflight.py](/D:/AI/pointer_gpf/v2/mcp_core/preflight.py)
- [flow_runner.py](/D:/AI/pointer_gpf/v2/mcp_core/flow_runner.py)
- [plugin_sync.py](/D:/AI/pointer_gpf/v2/mcp_core/plugin_sync.py)
- [plugin.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/plugin.gd)
- [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd)

## Verified Commands

These commands have already been executed successfully in this workspace.

### 1. V2 preflight

Fixed regression bundle:

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame
```

Observed bundle coverage:

- V2 unit tests
- `preflight_project`
- `basic_interactive_flow`
- `get_basic_flow_generation_questions`
- session-based `basicflow` generation
- default project-local `run_basic_flow`
- `analyze_basic_flow_staleness`
- stale override `run_basic_flow --allow-stale-basicflow`
- runtime guard checks (`FLOW_ALREADY_RUNNING`, `MULTIPLE_EDITOR_PROCESSES_DETECTED`)
- optional isolated-runtime validation through `--include-isolated-runtime`
- shared-desktop runs now report `isolation.status: shared_desktop`
- isolated-desktop runs now report `isolation.status: isolated_desktop`
- isolated-desktop runs now also report `host_desktop_name` and `separate_desktop: true`

```powershell
python -m v2.mcp_core.server --tool preflight_project --project-root D:\AI\pointer_gpf_testgame
```

Observed result:

- `ok: true`
- `script_uid_mismatch_count: 0`

### 2. V2 minimal flow

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\basic_minimal_flow.json
```

Observed result:

- `ok: true`
- `play_mode.status: entered_play_mode`
- `execution.status: passed`
- `step_count: 2`
- `project_close.status: verified`
- `project_close.project_process_count: 1`

### 3. V2 unit tests

```powershell
python -m unittest D:\AI\pointer_gpf\v2\tests\test_preflight.py D:\AI\pointer_gpf\v2\tests\test_flow_runner.py D:\AI\pointer_gpf\v2\tests\test_plugin_sync.py D:\AI\pointer_gpf\v2\tests\test_server.py
```

Observed result:

- latest fixed regression bundle currently exercises `Ran 66 tests`
- `OK`

### 4. V2 interactive flow

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\basic_interactive_flow.json
```

Observed result:

- `ok: true`
- `play_mode.status: entered_play_mode`
- `execution.status: passed`
- `step_count: 6`
- `project_close.status: verified`
- `project_close.project_process_count: 1`
- `plugin_sync.destination: D:\AI\pointer_gpf_testgame\addons\pointer_gpf`

### 5. V2 generated project basicflow

```powershell
python -m v2.mcp_core.server --tool generate_basic_flow --project-root D:\AI\pointer_gpf_testgame --answers-file D:\AI\pointer_gpf\pointer_gpf\tmp\basicflow_answers.json
```

Observed result:

- `ok: true`
- `status: generated`
- `flow_file: D:\AI\pointer_gpf_testgame\pointer_gpf\basicflow.json`
- `meta_file: D:\AI\pointer_gpf_testgame\pointer_gpf\basicflow.meta.json`
- detected target mode can now be project-specific instead of always generic
- validated project-specific path on `D:\AI\pointer_gpf_testgame`: `StartButton -> GameLevel -> GamePointerHud -> closeProject`
- current generation logic now recognizes:
  - `button_to_scene_with_runtime_anchor`
  - `button_to_scene_root`
  - `generic_runtime_probe`
- `step_count: 6`

Direct-answer generation:

```powershell
python -m v2.mcp_core.server --tool generate_basic_flow --project-root D:\AI\pointer_gpf_testgame --main-scene-is-entry true --tested-features "进入主流程,基础操作" --include-screenshot-evidence false
```

Observed result:

- `ok: true`
- `status: generated`
- no temporary `--answers-file` is required

Question contract:

```powershell
python -m v2.mcp_core.server --tool get_basic_flow_generation_questions --project-root D:\AI\pointer_gpf_testgame
```

Observed result:

- `ok: true`
- `status: questions_ready`
- `question_count: 3`
- includes `project_hint` for the current startup scene

Session-based question flow:

```powershell
python -m v2.mcp_core.server --tool start_basic_flow_generation_session --project-root D:\AI\pointer_gpf_testgame
python -m v2.mcp_core.server --tool answer_basic_flow_generation_session --project-root D:\AI\pointer_gpf_testgame --session-id <id> --question-id main_scene_is_entry --answer true
python -m v2.mcp_core.server --tool answer_basic_flow_generation_session --project-root D:\AI\pointer_gpf_testgame --session-id <id> --question-id tested_features --answer "进入主流程,基础操作"
python -m v2.mcp_core.server --tool answer_basic_flow_generation_session --project-root D:\AI\pointer_gpf_testgame --session-id <id> --question-id include_screenshot_evidence --answer false
python -m v2.mcp_core.server --tool complete_basic_flow_generation_session --project-root D:\AI\pointer_gpf_testgame --session-id <id>
```

Observed result:

- session starts with `status: awaiting_answer`
- each answer returns the next question
- final answer returns `status: ready_to_generate`
- completion writes `basicflow.json` + `basicflow.meta.json`
- a serial follow-up `run_basic_flow` passes

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame
```

Observed result after sync and clean restart:

- `ok: true`
- `execution.status: passed`
- `execution.flow_file: D:\AI\pointer_gpf_testgame\pointer_gpf\basicflow.json`
- `step_count: 6`
- `project_close.status: verified`
- current generated `basicflow` for this project is no longer just a generic visible-click probe

Stale-path override:

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --allow-stale-basicflow
```

Observed result:

- `ok: true`
- `execution.status: passed`
- `basicflow.status: stale`
- `basicflow.warning: ran stale basicflow because allow-stale-basicflow was set`
- `basicflow.last_successful_run_at` is updated

Stale analysis:

```powershell
python -m v2.mcp_core.server --tool analyze_basic_flow_staleness --project-root D:\AI\pointer_gpf_testgame
```

Observed result:

- `ok: true`
- `status: stale`
- returns `analysis_summary`
- returns `assumptions`
- returns `related_files`
- returns `baseline_project_file_summary` vs `current_project_file_summary`
- returns `recommended_next_step`

### 6. V2 flow conflict guard

Real regression command pattern:

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-runtime-guards.py --project-root D:\AI\pointer_gpf_testgame --check conflict
```

Observed result:

- second flow returns `FLOW_ALREADY_RUNNING`
- returned lock details include the first flow PID

### 7. V2 manual multi-editor detection

Real regression command pattern:

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-runtime-guards.py --project-root D:\AI\pointer_gpf_testgame --check multi-editor
```

Observed result:

- tool returns `MULTIPLE_EDITOR_PROCESSES_DETECTED`
- returned details include both project editor processes
- returned message tells the user to close extra editors first
- helper validation processes do not need extra visible console windows

### 8. V2 isolated runtime

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

Observed result:

- `ok: true`
- `tests_run: 64`
- includes `isolated_runtime_basic_minimal_flow`
- includes `isolated_runtime_basic_interactive_flow`
- both isolated flows return:
  - `execution_mode: isolated_runtime`
- `play_mode.status: launched_isolated_runtime`
- `execution.status: passed`
- `project_close.status: verified`
- `isolation.isolated: true`
- `isolation.status: isolated_desktop`
- `isolation.host_desktop_name: Default`
- `isolation.separate_desktop: true`
- host desktop activity validation now also passes with:
  - `host_activity.activity: mouse_wiggle`
  - `host_activity.iterations > 0`
  - isolated minimal + interactive flows still `passed`
- runtime-side mouse capture symptoms are now reduced further by bridge-side input guards, but those guards are still a mitigation layer rather than proof of full input isolation

## Current Technical Shape

V2 now supports this smallest closed loop:

1. sync plugin
2. preflight project
3. launch editor if needed
4. enter `play_mode`
5. execute a minimal file-bridge flow
6. verify teardown after `closeProject`
7. reject overlapping flow runs for the same project with `FLOW_ALREADY_RUNNING`
8. reject manual multi-editor runs with `MULTIPLE_EDITOR_PROCESSES_DETECTED`
9. generate and persist a project-local `basicflow`
10. run the project-local `basicflow` when `run_basic_flow` is called without `--flow-file`
11. warn when that project-local `basicflow` looks stale
12. optionally launch the tested runtime on a dedicated Windows desktop through `--execution-mode isolated_runtime`

The next product layer is now defined in docs:

- [v2-basic-flow-contract.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-contract.md)
- [v2-basic-flow-asset-model.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-asset-model.md)
- [v2-basic-flow-staleness-and-generation.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-staleness-and-generation.md)

## Important Design Decisions Already Made

### Keep

- file bridge execution
- runtime diagnostics
- explicit preflight
- external Godot test project workflow

### Reject

- putting all tools into one huge `server.py`
- mixing core testing with auto-fix, orchestration, NL routing, and Figma
- relying on old stale `runtime_gate.json` without checking real editor process state

## Current Blocking Point

There is no hard blocker at the end of phase 1.5.

Phase 1 minimal chain is already passing.

## Next Actions

Next phase should be:

1. wire the new question contract or session flow into the final conversational UX layer
2. update the fixed regression bundle so it covers question fetch, session flow, direct-answer `generate_basic_flow`, default `run_basic_flow`, stale analysis, and the stale override path
3. expand isolated-runtime validation from experimental launch coverage into a stricter user-input-isolation contract
4. decide whether generated default `basicflow` should evolve beyond the current generic visible-click probe when no conservative project-specific transition can be inferred

## Notes About External Project

Primary external validation project:

- `D:\AI\pointer_gpf_testgame`

Flow verification note:

- run flows serially against the same external project
- do not overlap two `run_basic_flow` executions against one shared `pointer_gpf/tmp`

This project previously had Godot resource UID drift issues which created false MCP failures.

Reference:

- [godot-resource-uid-drift-and-false-mcp-failures.md](/D:/AI/pointer_gpf/docs/godot-resource-uid-drift-and-false-mcp-failures.md)
