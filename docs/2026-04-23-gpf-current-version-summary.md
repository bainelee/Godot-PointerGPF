# 2026-04-23 GPF Current Version Summary

## Scope

This document summarizes the current repository version after the model-controlled repair workflow work.

It should be read together with:

- [v2-status.md](/D:/AI/pointer_gpf/docs/v2-status.md)
- [v2-handoff.md](/D:/AI/pointer_gpf/docs/v2-handoff.md)
- [v2-how-to-command-gpf.md](/D:/AI/pointer_gpf/docs/v2-how-to-command-gpf.md)
- [2026-04-23-gpf-model-controlled-repair-next-steps-detailed-plan.md](/D:/AI/pointer_gpf/docs/2026-04-23-gpf-model-controlled-repair-next-steps-detailed-plan.md)

## Current Product State

Pointer GPF V2 is now a Godot gray-box testing and bug-repair assistant with explicit tool boundaries.

Current working areas:

- project setup and `preflight`
- project-local `basicflow` generation, stale analysis, and execution
- real `play_mode` flow execution through the Godot plugin file bridge
- runtime teardown verification and flow conflict guards
- bug intake, observation, assertion/check generation, investigation planning, repro execution, fix planning, fix application, rerun, regression, and verification
- real-bug round baseline, seed, case, restore, and restore verification tooling
- generic runtime evidence through `sample`, cross-step `observe`, and evidence-backed `check`
- bounded model fix proposal validation and application
- top-level natural-language repair workflow through `repair_reported_bug`

Current explicit boundary:

- GPF does not classify every bug through an offline ruleset.
- The language model decides what evidence to collect and what edit to propose.
- GPF validates and executes bounded tools, persists artifacts, applies only validated edits, reruns repro, and runs regression.
- `repair_reported_bug` stops safely when model evidence plan or bounded fix proposal is missing.

## Current User Effect

For a request such as:

```text
敌人在受击之后不会按照预期闪烁一次红色，帮我自动修复这个 bug
```

The current system can:

1. normalize the bug report and expected behavior
2. observe project context and recent runtime evidence
3. plan a repro flow
4. accept a model-provided evidence plan for runtime `sample`, `observe`, and `check` steps
5. run a real `play_mode` repro flow
6. persist check results and runtime evidence
7. generate an evidence-backed fix plan
8. accept and validate a bounded model fix proposal
9. apply the edit only inside candidate files with unique text matches
10. rerun the same repro flow
11. run regression before reporting final success

If no evidence plan is supplied, the current expected status is:

- `status: awaiting_model_evidence_plan`
- `blocking_point: repair_reported_bug requires an accepted model evidence plan before running repro`
- `next_action: provide_evidence_plan_json_or_file`

If no bounded fix proposal is supplied after repro and fix planning, the expected status is:

- `status: bug_reproduced_awaiting_fix_proposal`
- `next_action: provide_fix_proposal_json_or_file`

## Developed Content

Runtime evidence:

- `runtime_bridge.gd` supports generic `sample`
- `runtime_bridge.gd` supports `observe` default window mode
- `runtime_bridge.gd` supports cross-step `observe` with `mode: "start"` and `mode: "collect"`
- `check` supports evidence-backed predicates
- flow reports and repro artifacts can carry runtime evidence records and summaries

Model evidence plans:

- `bug_evidence_plan.py` validates `--evidence-plan-json` and `--evidence-plan-file`
- `plan_bug_repro_flow` inserts accepted model evidence steps
- `trigger_window` observe requests are materialized around the trigger step
- executable checks include model evidence `check` steps

Fix planning and application:

- `plan_bug_fix` reads persisted repro evidence instead of rerunning repro
- `plan_bug_fix` carries runtime evidence summaries, compact records, evidence refs, and evidence-backed acceptance checks
- `bug_fix_proposal.py` validates and applies bounded model proposals
- `apply_bug_fix` can apply model proposals before falling back to older fixed strategies
- unsupported fixed strategies now return an explicit request for a bounded proposal

Top-level repair workflow:

- `bug_repair_workflow.py` implements `repair_reported_bug`
- `tool_dispatch.py` exposes `repair_reported_bug`
- `request_layer.py` routes explicit natural-language bug repair requests to `repair_reported_bug`
- `server.py` wires the workflow with repro, rerun, regression, and verification dependencies

Documentation:

- README and README.en now describe runtime evidence, bounded fix proposals, and `repair_reported_bug`
- `v2-status.md` records current implemented capabilities, limitations, verification results, and next actions
- `v2-handoff.md` records the current continuation path for a new conversation
- `v2-how-to-command-gpf.md` documents bug repair request shapes and the safe-stop statuses
- runtime evidence and natural-language bug auto-fix plans now include current implementation status

## Modified Code Areas

Core modules:

- [bug_evidence_plan.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_evidence_plan.py)
- [bug_fix_proposal.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_fix_proposal.py)
- [bug_repair_workflow.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repair_workflow.py)
- [bug_checks.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_checks.py)
- [bug_fix_application.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_fix_application.py)
- [bug_fix_planning.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_fix_planning.py)
- [bug_observation.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_observation.py)
- [bug_repro_execution.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repro_execution.py)
- [bug_repro_flow.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repro_flow.py)
- [contracts.py](/D:/AI/pointer_gpf/v2/mcp_core/contracts.py)
- [flow_runner.py](/D:/AI/pointer_gpf/v2/mcp_core/flow_runner.py)
- [request_layer.py](/D:/AI/pointer_gpf/v2/mcp_core/request_layer.py)
- [runtime_orchestration.py](/D:/AI/pointer_gpf/v2/mcp_core/runtime_orchestration.py)
- [server.py](/D:/AI/pointer_gpf/v2/mcp_core/server.py)
- [tool_dispatch.py](/D:/AI/pointer_gpf/v2/mcp_core/tool_dispatch.py)

Godot plugin:

- [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd)

Validation flows:

- [runtime_evidence_sample_flow.json](/D:/AI/pointer_gpf/v2/flows/runtime_evidence_sample_flow.json)
- [runtime_evidence_observe_flow.json](/D:/AI/pointer_gpf/v2/flows/runtime_evidence_observe_flow.json)

Tests:

- `test_bug_evidence_plan.py`
- `test_bug_fix_proposal.py`
- `test_bug_repair_workflow.py`
- updated bug, runtime, request, dispatch, server, and flow tests under [v2/tests](/D:/AI/pointer_gpf/v2/tests)

## Verification Evidence

Latest full repository unit test run:

```powershell
python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"
```

Observed:

- `Ran 199 tests in 1.790s`
- `OK`

Runtime evidence observe flow:

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_observe_flow.json
```

Observed:

- `ok: true`
- `execution.status: passed`
- `runtime_evidence_summary.record_count: 1`
- evidence id `scene_change_window`
- event scene `res://scenes/game_level.tscn`
- `project_close.status: verified`

Top-level repair smoke:

```powershell
python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame --bug-report "敌人在受击之后不会按照预期闪烁一次红色" --expected-behavior "敌人在受击之后应该闪烁一次红色" --steps-to-trigger "启动游戏|让敌人受击" --location-node Enemy
```

Observed:

- `ok: true`
- `schema: pointer_gpf.v2.reported_bug_repair.v1`
- `status: awaiting_model_evidence_plan`
- `blocking_point: repair_reported_bug requires an accepted model evidence plan before running repro`
- `next_action: provide_evidence_plan_json_or_file`

Fixed regression:

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame
```

Observed:

- `ok: true`
- `v2_unit_tests`: `Ran 97 tests`, `OK`
- `preflight_project`: `ok: true`
- `basic_interactive_flow`: `ok: true`
- `default_basicflow`: `ok: true`
- `basicflow_stale_override`: `ok: true`
- `runtime_guards`: `ok: true`

## Remaining Limits

The current version should not be described as fully automatic for all bugs.

Remaining limits:

- the model still has to generate a meaningful evidence plan
- the model still has to generate a valid bounded fix proposal
- behavior-bug validation still needs a real seeded round with baseline, injection, repro, evidence, fix proposal, rerun, regression, and restore
- candidate-file ranking can still be improved with richer static and runtime observations
- GPF still intentionally avoids unbounded arbitrary edits

## Next Recommended Work

1. Add a real behavior-bug validation round for a visual feedback bug.
2. Use `repair_reported_bug` with a model evidence plan and bounded fix proposal in that round.
3. Verify repro, evidence, fix application, rerun, regression, and restore.
4. Improve project observation so the model can choose better evidence targets from scenes, scripts, animations, signals, node paths, and materials.
5. Improve candidate-file ranking from runtime evidence refs and target node paths.
