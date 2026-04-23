# V2 Status

## Current Phase

V2 is in **phase 1.5**.

Current goal:

- keep the validated runtime chain stable
- treat `input isolation` as a later TODO unless it directly blocks the next core loop
- treat further `basicflow` productization expansion as a later TODO unless it directly blocks the next core loop
- return focus to GPF's main product loop: bug report -> analysis -> correct-state assertion -> repro flow -> reproduction -> fix -> re-verify
- the current bug-focused loop now also has persisted repro evidence, rerun support, and regression support after code changes
- avoid inheriting old system features such as open-ended NL routing, broad orchestration, and Figma workflows

Direction note:

- the current preferred direction is recorded in [2026-04-14-gpf-core-direction.md](/D:/AI/pointer_gpf/docs/2026-04-14-gpf-core-direction.md)
- the first concrete core-loop contract slice is recorded in [2026-04-14-gpf-bug-intake-and-assertion-contract.md](/D:/AI/pointer_gpf/docs/2026-04-14-gpf-bug-intake-and-assertion-contract.md)
- the current rule for using real bugs in the test project is recorded in [2026-04-21-gpf-bug-seeding-and-restoration-rules.md](/D:/AI/pointer_gpf/docs/2026-04-21-gpf-bug-seeding-and-restoration-rules.md)
- the current next-step implementation plan is recorded in [2026-04-22-gpf-real-bug-development-plan.md](/D:/AI/pointer_gpf/docs/2026-04-22-gpf-real-bug-development-plan.md)
- the current mainline follow-up after real-bug rounds is recorded in [2026-04-22-gpf-model-driven-bug-loop-plan.md](/D:/AI/pointer_gpf/docs/2026-04-22-gpf-model-driven-bug-loop-plan.md)
- the current concrete user-scenario target for new-project bug auto-fix is recorded in [2026-04-22-gpf-new-project-natural-language-bug-auto-fix-plan.md](/D:/AI/pointer_gpf/docs/2026-04-22-gpf-new-project-natural-language-bug-auto-fix-plan.md)
- the current runtime-evidence implementation plan is recorded in [2026-04-23-gpf-generic-runtime-evidence-primitives-plan.md](/D:/AI/pointer_gpf/docs/2026-04-23-gpf-generic-runtime-evidence-primitives-plan.md)
- the current model-controlled repair execution plan and verification record is [2026-04-23-gpf-model-controlled-repair-next-steps-detailed-plan.md](/D:/AI/pointer_gpf/docs/2026-04-23-gpf-model-controlled-repair-next-steps-detailed-plan.md)
- the current version summary is [2026-04-23-gpf-current-version-summary.md](/D:/AI/pointer_gpf/docs/2026-04-23-gpf-current-version-summary.md)

Authoritative current-doc order:

1. [README.md](/D:/AI/pointer_gpf/README.md)
2. [v2-status.md](/D:/AI/pointer_gpf/docs/v2-status.md)
3. [v2-handoff.md](/D:/AI/pointer_gpf/docs/v2-handoff.md)
4. [v2-how-to-command-gpf.md](/D:/AI/pointer_gpf/docs/v2-how-to-command-gpf.md)
5. [2026-04-23-gpf-current-version-summary.md](/D:/AI/pointer_gpf/docs/2026-04-23-gpf-current-version-summary.md)
6. [2026-04-23-gpf-model-controlled-repair-next-steps-detailed-plan.md](/D:/AI/pointer_gpf/docs/2026-04-23-gpf-model-controlled-repair-next-steps-detailed-plan.md)

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
- `collect_bug_report`
- `analyze_bug_report`
- `observe_bug_context`
- `define_bug_checks`
- `define_bug_assertions`
- `plan_bug_investigation`
- `plan_bug_repro_flow`
- `run_bug_repro_flow`
- `rerun_bug_repro_flow`
- `plan_bug_fix`
- `apply_bug_fix`
- `run_bug_fix_regression`
- `verify_bug_fix`
- `repair_reported_bug`
- `start_test_project_bug_round`
- `seed_test_project_bug`
- `restore_test_project_bug_round`
- bug-focused repro results are now persisted under `pointer_gpf/tmp/last_bug_repro_result.json`
- bug-focused rerun verification is now persisted under `pointer_gpf/tmp/last_bug_fix_verification.json`
- bug-fix regression results are now persisted under `pointer_gpf/tmp/last_bug_fix_regression.json`
- bug-fix verification summary is now persisted under `pointer_gpf/tmp/last_bug_fix_verification_summary.json`
- real-bug round state is now persisted under `pointer_gpf/tmp/bug_dev_rounds/<round_id>/`
- bug rounds now write `baseline_manifest.json`, `bug_injection_plan.json`, `restore_plan.json`, and per-bug `bug_cases/<bug_id>.json`
- the current injected real bug kinds include:
  - `button_signal_or_callback_broken`
  - `scene_transition_not_triggered`
  - `button_node_renamed_in_scene`
  - `pointer_hud_not_spawned`
- bug-focused repro classification now separates:
  - `precondition_failed`
  - `trigger_failed`
  - `bug_reproduced`
  - `bug_not_reproduced`
  - `runtime_invalid`
- `observe_bug_context` now returns a model-usable summary of:
  - startup scene
  - bug intake and bug analysis
  - current assertion set
  - project-local basicflow hints
  - latest runtime diagnostics summary
  - latest persisted repro result summary
  - latest fix verification summary
  - candidate file read order
- `plan_bug_investigation` now returns:
  - grouped runtime actions
  - executable check candidates
  - a machine-readable `executable_check_set`
  - failure branches by repro status
  - repair focus candidates
  - recommended next tools for the current bug workflow
- `define_bug_checks` now returns a bounded executable check set with:
  - assertion-linked check ids
  - mapped flow step ids when a candidate flow step already exists
  - explicit runtime actions such as `wait` and `check`
- `run_bug_repro_flow` now persists:
  - `executable_checks`
  - `check_results`
  - `check_summary`
- `plan_bug_fix` now reads persisted repro check evidence and returns:
  - `evidence_summary`
  - `acceptance_checks`
  - candidate files ordered with observation evidence
  - fix goals derived from failed checks when possible
- `plan_bug_fix` no longer reruns repro internally; it reads the persisted repro result for the current project
- `observe` can run as a cross-step event observer with `mode: "start"` and `mode: "collect"`
- `plan_bug_repro_flow` can materialize a model `trigger_window` observe step around the trigger action
- `apply_bug_fix` can apply a bounded model fix proposal from `--fix-proposal-json` or `--fix-proposal-file`
- `repair_reported_bug` runs the explicit sequence for natural-language bug repair requests and stops with `blocking_point` plus `next_action` when the model still needs to provide an evidence plan or fix proposal

## Current Limitation

The repository now has stable real-bug round management, but the model still does not have enough structured observation and planning support to drive the full bug loop by itself.

What is already implemented:

- baseline recording for the external test project before bug injection
- real bug injection tools
- bug-case files that bind repair runs to a known injected bug
- restore tools that return the test project to the recorded baseline
- restore verification written to a durable result file
- generic runtime evidence contracts for `sample`, `observe`, and evidence-backed `check`
- runtime evidence records and summaries in flow reports, runtime orchestration results, and bug repro artifacts when evidence is present
- real `play_mode` validation for a node-property `sample` flow
- real `play_mode` validation for a cross-step `observe` flow
- model-provided evidence plans can now be loaded from `--evidence-plan-json` or `--evidence-plan-file`
- accepted model evidence `sample`, `observe`, and `check` steps are inserted into `plan_bug_repro_flow` candidate flows
- model evidence `check` steps are now included in executable check sets
- `plan_bug_fix` now preserves runtime evidence summaries, compact records, evidence refs, and evidence-backed acceptance checks
- bounded model fix proposals can be applied inside candidate files without requiring a fixed strategy kind
- natural-language bug repair requests can route to `repair_reported_bug`

What is still limited:

- bug reasoning is still stronger than bug execution planning
- the model still does not reliably generate structured evidence plans from arbitrary bug reports without an external model step
- the model still does not yet generate a rich executable investigation plan by default
- the model still must provide the bounded fix proposal; the deterministic MCP layer does not invent arbitrary code edits

Current judgment:

- the repository now has controlled test-project bug lifecycle management
- the next implementation area inside bug work should validate the new generic workflow against a real behavior bug, then improve model-side evidence and edit proposal quality

## Deferred TODO

These areas are not the current mainline, unless they directly block the new core bug loop:

- stronger `input isolation` guarantees and validation
- more `basicflow` productization work beyond the current already-working scope
- regression-bundle final cleanup for `play_mode` runs: after the full module/CLI test set plus fixed regression finishes, exit all remaining Godot processes for the current project only
- shared-desktop `play_mode` hang / `未响应` symptom after regression teardown, especially when the user manually interacts with the leftover project editor window

Current judgment:

- `input isolation` should be recorded as later-stage work
- additional `basicflow` expansion should also be recorded as later-stage work
- the regression final-cleanup issue should also be recorded as later-stage work
- the real-bug round system should now be treated as validation infrastructure rather than as the main product center
- the next mainline should move toward model-driven bug investigation, model-driven executable checks, and evidence-backed repair planning

Deferred cleanup constraint:

- when this cleanup work is implemented, it must target only Godot processes that belong to the current `--project-root`
- if other Godot editors or runtimes from different projects are open on the same machine, they must not be terminated by this cleanup
- the current observed behavior is that `closeProject` + teardown verification in shared `play_mode` accepts one remaining editor process for the project, so the fixed regression bundle can end with a leftover project editor window

## Next Mainline Direction

GPF should now be treated as:

- a Godot gray-box testing tool
- a bug reproduction tool
- a bug fixing assistant

The next core loop should be:

1. the user describes a bug in natural language
2. GPF analyzes likely causes and affected areas
3. GPF defines the correct non-bug state as explicit assertions
4. GPF designs or updates a flow that can reach the bug
5. GPF runs the flow to confirm reproduction
6. GPF applies a fix
7. GPF reruns the same bug-focused flow after the code change
8. GPF runs regression after the bug-focused rerun passes
9. GPF reports one final verification result

This should become the main product direction after the completed server split.

The first concrete implementation slice inside that direction should be:

1. `collect_bug_report`
2. `analyze_bug_report`
3. `define_bug_assertions`

The next concrete implementation slice after the current repair-workflow code is now:

1. strengthen structured project and runtime observation for bug work
2. add a model-driven investigation-plan step that chooses actions and checks
3. let the model generate bounded executable checks instead of relying only on a small fixed catalog
4. keep bounded fix proposal support as the primary broader edit path instead of default growth by fixed bug-kind handlers
5. keep real-bug rounds as the validation method for the above work

The concrete product target for those steps is now also explicit:

1. the user installs GPF into a new project
2. the user reports a real bug in natural language
3. GPF reproduces it in real `play_mode`
4. GPF applies a bounded fix
5. GPF reruns the bug flow and regression before reporting the final result

Important rule for that target:

1. do not turn one user example into one product feature
2. let the language model decide where the bug likely comes from, what should be checked, and what should be changed
3. keep GPF focused on generic bounded tools for observation, execution, editing, and verification

The next concrete runtime-side plan for that rule is:

1. add generic runtime read, sample, and observe primitives
2. persist timestamped evidence in repro artifacts
3. let structured bug checks reference evidence ids instead of only one `hint`

Current implementation status for that plan:

1. `sample` and `observe` actions are accepted by flow contracts
2. `runtime_bridge.gd` implements generic `sample` and `observe`
3. `check` can evaluate an `evidenceRef` with a bounded predicate
4. flow reports and `run_basic_flow_tool` results now include runtime evidence records and summaries
5. a real `play_mode` sample flow has verified timestamped node-property sampling
6. [runtime_evidence_sample_flow.json](/D:/AI/pointer_gpf/v2/flows/runtime_evidence_sample_flow.json) passed against `D:\AI\pointer_gpf_testgame` with `runtime_evidence_summary.record_count: 1`
7. [bug_evidence_plan.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_evidence_plan.py) validates bounded model evidence plans
8. `plan_bug_repro_flow` can insert model-provided `sample`, `observe`, and `check` steps into candidate repro flows
9. `plan_bug_fix` now carries evidence refs into `evidence_summary`, `candidate_files`, `fix_goals`, and `acceptance_checks`
10. [runtime_evidence_observe_flow.json](/D:/AI/pointer_gpf/v2/flows/runtime_evidence_observe_flow.json) passed against `D:\AI\pointer_gpf_testgame` with `runtime_evidence_summary.record_count: 1`
11. [bug_fix_proposal.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_fix_proposal.py) supports bounded model edit proposal validation and application
12. [bug_repair_workflow.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repair_workflow.py) implements `repair_reported_bug`

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

Latest observed fixed regression result:

- `ok: true`
- `v2_unit_tests`: `Ran 97 tests`, `OK`
- `preflight_project`: `ok: true`
- `basic_interactive_flow`: `ok: true`
- `default_basicflow`: `ok: true`
- `basicflow_stale_override`: `ok: true`
- `runtime_guards`: `ok: true`

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

- the latest full V2 unit-test run in this workspace exercised `Ran 199 tests`
- `OK`

Model evidence plan CLI smoke:

```powershell
python -m v2.mcp_core.server --tool plan_bug_repro_flow --project-root D:\AI\pointer_gpf_testgame --bug-report "点击开始游戏后按钮状态没有变化" --expected-behavior "点击后按钮状态应该变化" --steps-to-trigger "启动游戏|点击开始按钮" --location-node StartButton --evidence-plan-file D:\AI\pointer_gpf\pointer_gpf\tmp\model_evidence_plan_cli_smoke.json
```

Observed result:

- `ok: true`
- `model_evidence_plan_status: accepted`
- `planned_runtime_evidence_step_count: 2`
- `evidence_refs_required: ["startbutton_visible_window"]`
- `evidence_refs_produced: ["startbutton_visible_window"]`

### 3.1 Runtime evidence sample flow

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_sample_flow.json
```

Observed result:

- `ok: true`
- `execution.status: passed`
- `runtime_evidence_summary.record_count: 1`
- `runtime_evidence_refs: ["startbutton_visible_window"]`
- `runtime_evidence_records[0].record_type: sample_result`
- `project_close.status: verified`

### 3.2 Runtime evidence observe flow

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_observe_flow.json
```

Observed result:

- `ok: true`
- `execution.status: passed`
- `runtime_evidence_summary.record_count: 1`
- evidence id `scene_change_window`
- observed event scene `res://scenes/game_level.tscn`
- `project_close.status: verified`

### 3.3 Top-level repair smoke

```powershell
python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame --bug-report "敌人在受击之后不会按照预期闪烁一次红色" --expected-behavior "敌人在受击之后应该闪烁一次红色" --steps-to-trigger "启动游戏|让敌人受击" --location-node Enemy
```

Observed result:

- `ok: true`
- `schema: pointer_gpf.v2.reported_bug_repair.v1`
- `status: awaiting_model_evidence_plan`
- `blocking_point: repair_reported_bug requires an accepted model evidence plan before running repro`
- `next_action: provide_evidence_plan_json_or_file`

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

1. add a real behavior-bug validation round that uses `repair_reported_bug` with a model evidence plan and bounded fix proposal
2. improve model-facing project observation so the model can choose better evidence plans from real scenes, scripts, animations, signals, and node paths
3. improve candidate-file ranking from runtime evidence refs and target node paths
4. keep avoiding per-bug fixed branches; the model should choose the relevant checks and candidate files from project facts and runtime evidence

## Notes About External Project

Primary external validation project:

- `D:\AI\pointer_gpf_testgame`

Flow verification note:

- run flows serially against the same external project
- do not overlap two `run_basic_flow` executions against one shared `pointer_gpf/tmp`

This project previously had Godot resource UID drift issues which created false MCP failures.

Reference:

- [godot-resource-uid-drift-and-false-mcp-failures.md](/D:/AI/pointer_gpf/docs/godot-resource-uid-drift-and-false-mcp-failures.md)
