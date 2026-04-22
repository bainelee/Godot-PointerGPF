# V2 Handoff

## Read First

When continuing V2 work in a new conversation, read these files first:

1. [v2-status.md](/D:/AI/pointer_gpf/docs/v2-status.md)
2. [v2-architecture.md](/D:/AI/pointer_gpf/docs/v2-architecture.md)
3. [v2-how-to-command-gpf.md](/D:/AI/pointer_gpf/docs/v2-how-to-command-gpf.md)
4. [v2-natural-language-boundary-principles.md](/D:/AI/pointer_gpf/docs/v2-natural-language-boundary-principles.md)
5. [2026-04-13-v2-server-split-plan.md](/D:/AI/pointer_gpf/docs/2026-04-13-v2-server-split-plan.md)
6. [v2-basic-flow-user-intent.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-user-intent.md)
7. [v2-basic-flow-contract.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-contract.md)
8. [v2-basic-flow-asset-model.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-asset-model.md)
9. [v2-basic-flow-staleness-and-generation.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-staleness-and-generation.md)
10. [v2-plugin-runtime-map.md](/D:/AI/pointer_gpf/docs/v2-plugin-runtime-map.md)
11. [godot-resource-uid-drift-and-false-mcp-failures.md](/D:/AI/pointer_gpf/docs/godot-resource-uid-drift-and-false-mcp-failures.md)
12. [2026-04-14-gpf-core-direction.md](/D:/AI/pointer_gpf/docs/2026-04-14-gpf-core-direction.md)
13. [2026-04-14-gpf-bug-intake-and-assertion-contract.md](/D:/AI/pointer_gpf/docs/2026-04-14-gpf-bug-intake-and-assertion-contract.md)
14. [2026-04-21-gpf-stage-status-and-gap.md](/D:/AI/pointer_gpf/docs/2026-04-21-gpf-stage-status-and-gap.md)
15. [2026-04-21-gpf-next-development-plan.md](/D:/AI/pointer_gpf/docs/2026-04-21-gpf-next-development-plan.md)
16. [2026-04-21-gpf-bug-seeding-and-restoration-rules.md](/D:/AI/pointer_gpf/docs/2026-04-21-gpf-bug-seeding-and-restoration-rules.md)
17. [2026-04-22-gpf-real-bug-development-plan.md](/D:/AI/pointer_gpf/docs/2026-04-22-gpf-real-bug-development-plan.md)
18. [2026-04-22-gpf-model-driven-bug-loop-plan.md](/D:/AI/pointer_gpf/docs/2026-04-22-gpf-model-driven-bug-loop-plan.md)

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

The server-split refactor is also no longer just planned.
The current `main` branch now has a materially split V2 core:

- `server.py` as the entry shell
- `tool_dispatch.py` as the top-level tool branch layer
- `request_layer.py` as the bounded user-request layer
- `runtime_orchestration.py` as the runtime execution coordinator
- `process_probe.py` as the Godot process / editor probe layer
- `teardown_verification.py` as the stop-verification and flow-lock layer

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
- V2 `get_basic_flow_user_intents` returns a small structured intent catalog plus `primary_recommendation` / `secondary_actions`, so the upper conversational layer can pick `run_basic_flow`, `generate_basic_flow`, or `analyze_basic_flow_staleness` based on project state
- V2 `resolve_basic_flow_user_request` is now a thin adapter that matches a small set of basicflow-related user phrases and returns the current project-aware recommended action
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
- the latest repository-wide V2 unit-test run in this workspace passed with `Ran 170 tests`, `OK`
- the latest fixed regression bundle against `D:\AI\pointer_gpf_testgame` reported `v2_unit_tests` with `Ran 91 tests`, `OK`
- V2 rejects overlapping flow runs for one project with `FLOW_ALREADY_RUNNING`
- V2 rejects manual multi-editor runs for one project with `MULTIPLE_EDITOR_PROCESSES_DETECTED`
- user language like `跑基础测试流程` should be interpreted as `run_basic_flow`

Current product-priority judgment:

- `input isolation` should now be treated as later TODO work unless it directly blocks the next core bug loop
- further `basicflow` expansion should also be treated as later TODO work unless it directly blocks the next core bug loop
- regression-bundle final Godot cleanup should also be treated as later TODO work unless it directly blocks the next core bug loop
- the next mainline should return to the core GPF product loop described in [2026-04-14-gpf-core-direction.md](/D:/AI/pointer_gpf/docs/2026-04-14-gpf-core-direction.md)

Current bug-focused implementation status:

- `collect_bug_report`, `analyze_bug_report`, `define_bug_assertions`, `plan_bug_repro_flow`, `run_bug_repro_flow`, `rerun_bug_repro_flow`, `plan_bug_fix`, `apply_bug_fix`, `run_bug_fix_regression`, and `verify_bug_fix` now exist on the CLI/tool path
- `observe_bug_context`, `define_bug_checks`, and `plan_bug_investigation` now also exist on the CLI/tool path
- `start_test_project_bug_round`, `seed_test_project_bug`, and `restore_test_project_bug_round` now also exist on the CLI/tool path
- bug-focused repro no longer classifies by failed step guessing; it now classifies by execution phase
- bug-focused repro results are persisted under `pointer_gpf/tmp/last_bug_repro_result.json`
- rerun verification after a code change is persisted under `pointer_gpf/tmp/last_bug_fix_verification.json`
- regression results after a code change are persisted under `pointer_gpf/tmp/last_bug_fix_regression.json`
- the combined verification summary is persisted under `pointer_gpf/tmp/last_bug_fix_verification_summary.json`
- `plan_bug_fix` now reads persisted repro evidence instead of running a new repro internally
- planner logic has been reduced to base flow reuse, explicit trigger insertion, and explicit precondition/postcondition steps
- `observe_bug_context` now summarizes startup scene, current assertion set, project-local basicflow hints, runtime diagnostics, latest repro evidence, latest fix verification, and candidate file read order for model use
- `define_bug_checks` now returns a bounded executable check set with assertion-linked check ids and mapped flow step ids where available
- `plan_bug_investigation` now turns that observation into grouped runtime actions, executable check candidates, a machine-readable executable check set, failure branches, and repair focus candidates
- bug-focused repro artifacts now also persist `executable_checks`, `check_results`, and `check_summary`
- `plan_bug_fix` now reads persisted repro check evidence and returns `evidence_summary` plus `acceptance_checks` for rerun
- real-bug rounds now persist under `pointer_gpf/tmp/bug_dev_rounds/<round_id>/`
- each round now records `baseline_manifest.json`, `bug_injection_plan.json`, `restore_plan.json`, and per-bug `bug_cases/<bug_id>.json`
- the current injected real bug kinds include:
  - `button_signal_or_callback_broken`
  - `scene_transition_not_triggered`
  - `button_node_renamed_in_scene`
  - `pointer_hud_not_spawned`

Important current limitation:

- the repository now implements baseline recording, bug injection, bug-case files, and restore for the external test project
- the current mainline limitation is broader than one missing fix strategy: the model still does not have enough structured observation and planning support to drive the whole bug loop by itself
- `apply_bug_fix` is still narrower than the intended product direction because it relies on a small fixed strategy set instead of a broader evidence-backed edit workflow
- newer injected bug kinds can be used for controlled real-bug rounds, but those rounds should now be treated mainly as evaluation infrastructure for model-driven bug work
- future development must continue following [2026-04-21-gpf-bug-seeding-and-restoration-rules.md](/D:/AI/pointer_gpf/docs/2026-04-21-gpf-bug-seeding-and-restoration-rules.md)
- the implementation order that led to the current round system is defined in [2026-04-22-gpf-real-bug-development-plan.md](/D:/AI/pointer_gpf/docs/2026-04-22-gpf-real-bug-development-plan.md)
- the mainline follow-up after that round system is defined in [2026-04-22-gpf-model-driven-bug-loop-plan.md](/D:/AI/pointer_gpf/docs/2026-04-22-gpf-model-driven-bug-loop-plan.md)

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
- `get_basic_flow_user_intents`
- session-based `basicflow` generation
- default project-local `run_basic_flow`
- `analyze_basic_flow_staleness`
- stale override `run_basic_flow --allow-stale-basicflow`
- runtime guard checks
- optional isolated runtime minimal + interactive flows

Current test shape after the split:

- `test_server.py` is now mainly for CLI smoke and compatibility wrappers
- request behavior is increasingly covered in `test_request_layer.py`
- runtime orchestration behavior is increasingly covered in `test_runtime_orchestration.py`
- process probes are covered in `test_process_probe.py`
- teardown / lock behavior is covered in `test_teardown_verification.py`
- top-level dispatch behavior is covered in `test_tool_dispatch.py`

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

After the current repair-workflow implementation, the next target is no longer more planner or assertion refinement by default.

Preferred next target:

1. strengthen structured project and runtime observation for bug work
2. add a model-driven investigation-plan step that chooses runtime actions and checks
3. let the model generate bounded executable checks from project evidence
4. move fix planning away from default growth by fixed bug-kind handlers
5. keep the real-bug round system stable as validation infrastructure

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
- the top-level user-request path is now split into `plan_user_request` and `handle_user_request`
  - `plan_user_request` resolves the supported high-level request into `tool + args + readiness`
  - `handle_user_request` currently auto-executes only safe next-step tools, not real runtime flow execution
- the server split is now materially implemented
  - `server.py` no longer owns the main request catalogs or runtime helper bodies
  - `tool_dispatch.py` now owns the main tool branch logic formerly in `main()`
  - `process_probe.py` and `teardown_verification.py` now hold the narrower runtime helper concerns that previously sat inside the orchestration path
  - current follow-up should prefer documentation and test hygiene over more structural splitting, unless a new high-level domain forces another boundary change
- `input isolation` remains important but is now considered later TODO work, not the immediate mainline
- `basicflow` remains important but is now considered "good enough for now" unless a bug-focused flow requirement exposes a real missing piece
- there is also a deferred regression-cleanup issue in shared `play_mode`
  - after the current module/CLI test collection plus `verify-v2-regression.py`, one Godot editor process for the active project can remain alive by design
  - this matches the current teardown contract, because `project_close.status: verified` only requires play mode to stop and the project editor-process count to be `<= 1`
  - users may see the leftover project editor window become `未响应` if they interact with it during or after teardown
  - future cleanup work should explicitly exit all remaining Godot processes for the current project after the regression bundle finishes
  - that cleanup must stay project-scoped: do not kill unrelated Godot editors or runtimes that belong to other projects open on the same machine

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
继续 pointer_gpf 的 V2 工作。先读 docs/v2-status.md、docs/v2-architecture.md、docs/v2-plugin-runtime-map.md、docs/v2-handoff.md、docs/2026-04-21-gpf-bug-seeding-and-restoration-rules.md、docs/2026-04-22-gpf-real-bug-development-plan.md、docs/2026-04-22-gpf-model-driven-bug-loop-plan.md，然后按 AGENTS.md 要求先运行 python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame，复述关键输出。接着检查当前 real-bug round 工具、bug case 文件和恢复结果是否还与代码一致；如果一致，优先补模型可用的项目/运行观察、bug investigation plan 和 bounded executable checks，不要默认继续堆固定 bug 类型或固定修复分支。
```
