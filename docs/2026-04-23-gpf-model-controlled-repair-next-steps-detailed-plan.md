# 2026-04-23 GPF Model-Controlled Repair Next Steps Detailed Plan

## Purpose

This document defines the next detailed implementation plan after generic runtime evidence primitives have started to exist.

The target remains:

- the model decides what the bug likely is
- GPF provides bounded MCP tools for project observation, runtime evidence, edit proposal, edit application, rerun, and regression
- no new implementation step should become a dedicated feature for one named bug example

Canonical user scenario:

- `敌人在受击之后不会按照预期闪烁一次红色，帮我自动修复这个 bug`

This scenario is an acceptance example only.
It must not become a hard-coded bug category.

## Current Facts

Already implemented:

- `bug_repair` request intake exists and can map natural-language repair requests to structured bug intake.
- `sample`, `observe`, and evidence-backed `check` contracts exist.
- `runtime_bridge.gd` can return timestamped sample evidence.
- `flow_runner.py`, `runtime_orchestration.py`, and `bug_repro_execution.py` can carry runtime evidence records.
- `runtime_evidence_sample_flow.json` passed in real `play_mode`.
- `bug_evidence_plan.py` now validates model-provided evidence plans from `--evidence-plan-json` or `--evidence-plan-file`.
- `plan_bug_repro_flow` now inserts accepted model evidence steps into the candidate repro flow, including `trigger_window` observers that start before a trigger and collect after it.
- `build_executable_checks` now includes model evidence `check` steps as executable checks.
- `plan_bug_fix` now carries runtime evidence summaries, compact evidence records, evidence refs, and evidence-backed acceptance checks.
- `apply_bug_fix` can apply a bounded model fix proposal without requiring one of the older fixed strategy kinds.
- `repair_reported_bug` now exists as the top-level tool for natural-language bug repair requests.

Current facts that still limit the target:

- the deterministic MCP layer does not invent evidence plans; the model must provide `--evidence-plan-json` or `--evidence-plan-file` when generic runtime evidence is needed
- the deterministic MCP layer does not invent code edits; the model must provide `--fix-proposal-json` or `--fix-proposal-file` before `apply_bug_fix` can use the broader edit path
- the next real validation work should seed a behavior bug and prove repro, evidence, bounded edit, rerun, regression, and restore on that case

## Implementation Result On 2026-04-23

Implemented before the final three-step execution:

- [bug_evidence_plan.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_evidence_plan.py) loads and validates bounded model evidence plans.
- [server.py](/D:/AI/pointer_gpf/v2/mcp_core/server.py) accepts `--evidence-plan-json` and `--evidence-plan-file`.
- [bug_repro_flow.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repro_flow.py) adds accepted model evidence steps by phase and reports produced/required evidence refs.
- [bug_checks.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_checks.py) treats model evidence `check` steps as executable checks.
- [bug_fix_planning.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_fix_planning.py) includes runtime evidence summaries, compact records, evidence refs, and evidence-backed acceptance checks.

Implemented in the final three-step execution:

- [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd) supports `observe` `mode: "start"` and `mode: "collect"` so event windows can span a trigger action.
- [bug_repro_flow.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repro_flow.py) materializes `trigger_window` observe requests as start observer -> trigger -> collect observer.
- [runtime_evidence_observe_flow.json](/D:/AI/pointer_gpf/v2/flows/runtime_evidence_observe_flow.json) validates cross-step observation in real `play_mode`.
- [bug_fix_proposal.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_fix_proposal.py) loads, validates, persists, and applies bounded model edit proposals.
- [bug_fix_application.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_fix_application.py) uses a valid model fix proposal before falling back to older fixed strategies.
- [bug_repair_workflow.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repair_workflow.py) implements `repair_reported_bug`.
- [request_layer.py](/D:/AI/pointer_gpf/v2/mcp_core/request_layer.py) routes natural-language bug repair requests to `repair_reported_bug`.
- [tool_dispatch.py](/D:/AI/pointer_gpf/v2/mcp_core/tool_dispatch.py) exposes `repair_reported_bug` through the CLI/tool dispatcher.

Verified:

- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_evidence_plan.py D:\AI\pointer_gpf\v2\tests\test_bug_repro_flow.py D:\AI\pointer_gpf\v2\tests\test_bug_checks.py D:\AI\pointer_gpf\v2\tests\test_bug_fix_planning.py` returned `Ran 19 tests in 0.094s`, `OK`.
- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_server.py D:\AI\pointer_gpf\v2\tests\test_tool_dispatch.py` returned `Ran 76 tests in 0.801s`, `OK`.
- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_evidence_plan.py D:\AI\pointer_gpf\v2\tests\test_bug_repro_flow.py D:\AI\pointer_gpf\v2\tests\test_bug_fix_proposal.py D:\AI\pointer_gpf\v2\tests\test_bug_fix_application.py D:\AI\pointer_gpf\v2\tests\test_bug_repair_workflow.py D:\AI\pointer_gpf\v2\tests\test_request_layer.py D:\AI\pointer_gpf\v2\tests\test_tool_dispatch.py` returned `Ran 49 tests in 0.148s`, `OK`.
- `python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"` returned `Ran 199 tests in 1.790s`, `OK`.
- `python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_observe_flow.json` returned `ok: true`, `execution.status: passed`, `runtime_evidence_summary.record_count: 1`, and evidence `scene_change_window` with event scene `res://scenes/game_level.tscn`.
- `python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame --bug-report "敌人在受击之后不会按照预期闪烁一次红色" --expected-behavior "敌人在受击之后应该闪烁一次红色" --steps-to-trigger "启动游戏|让敌人受击" --location-node Enemy` returned `status: awaiting_model_evidence_plan`, `blocking_point: repair_reported_bug requires an accepted model evidence plan before running repro`, and `next_action: provide_evidence_plan_json_or_file`.
- `python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame` returned `ok: true`; the bundle included `v2_unit_tests` with `Ran 97 tests`, `preflight_project`, `basic_interactive_flow`, `default_basicflow`, `basicflow_stale_override`, and `runtime_guards`.
- A CLI smoke test with `--evidence-plan-file` against `D:\AI\pointer_gpf_testgame` returned `model_evidence_plan_status: accepted`, `planned_runtime_evidence_step_count: 2`, `evidence_refs_required: ["startbutton_visible_window"]`, and `evidence_refs_produced: ["startbutton_visible_window"]`.

## Design Rule

The next implementation must make this possible:

1. the model reads bug intake and project evidence
2. the model chooses generic evidence requests
3. GPF validates that those requests are bounded and safe
4. GPF materializes them into a real `play_mode` flow
5. GPF persists evidence
6. the model uses evidence to plan the fix
7. GPF applies only bounded, evidence-backed edits
8. GPF verifies with rerun and regression

The implementation must not do this:

- classify every bug into a fixed product taxonomy
- add a repair branch only for enemy red flash
- claim success without a real repro rerun and regression

## Phase 1: Model Evidence Plan Input Contract

### Code Changes

Add a new module:

- `v2/mcp_core/bug_evidence_plan.py`

Responsibilities:

- load evidence plans from `--evidence-plan-json` or `--evidence-plan-file`
- validate allowed runtime actions: `sample`, `observe`, `check`, `wait`, `click`
- validate bounded timing:
  - max evidence steps per plan
  - max `windowMs`
  - min `intervalMs`
  - no filesystem paths
  - no script execution
- normalize field names:
  - `phase`
  - `target`
  - `metric`
  - `event`
  - `predicate`
  - `evidenceKey`
  - `evidenceRef`
- return either a normalized plan or a structured rejection reason

Modify:

- `v2/mcp_core/server.py`
- `v2/mcp_core/tool_dispatch.py`
- `v2/mcp_core/bug_repro_flow.py`
- `v2/tests/test_server.py`
- `v2/tests/test_bug_repro_flow.py` if the file exists, otherwise add it

New CLI args:

- `--evidence-plan-json`
- `--evidence-plan-file`

New output fields from `plan_bug_repro_flow`:

- `model_evidence_plan_status`
- `model_evidence_plan`
- `rejected_evidence_plan_reasons`
- `planned_runtime_evidence_step_count`

### Acceptance

`plan_bug_repro_flow` can accept a model-provided generic evidence plan such as:

```json
{
  "steps": [
    {
      "phase": "post_trigger",
      "id": "sample_enemy_modulate_after_hit",
      "action": "sample",
      "target": {"hint": "node_name:Enemy"},
      "metric": {"kind": "node_property", "property_path": "modulate"},
      "windowMs": 500,
      "intervalMs": 50,
      "evidenceKey": "enemy_modulate_after_hit"
    },
    {
      "phase": "post_trigger",
      "id": "check_enemy_modulate_changed",
      "action": "check",
      "checkType": "node_property_changes_within_window",
      "evidenceRef": "enemy_modulate_after_hit",
      "predicate": {"operator": "changed_from_baseline"}
    }
  ]
}
```

Expected behavior:

- accepted plans appear in the candidate flow
- unsafe or malformed plans are rejected with explicit reasons
- no bug-specific branch is added

Current status:

- implemented for `sample`, `check`, `wait`, and `click`
- `observe` is intentionally rejected until Phase 2

## Phase 2: Cross-Step Event Observation Window

### Why This Is Required

Sequential `observe` is not enough for common bugs.

If a signal or animation starts during the same frame as a click or hit action, then:

- `observe` before `click` can finish before the event happens
- `observe` after `click` can start too late

Therefore GPF needs a bounded observer that can start before a trigger and collect after the trigger.

### Code Changes

Modify:

- `v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd`
- `v2/mcp_core/contracts.py`
- `v2/mcp_core/flow_runner.py`
- `v2/tests/test_flow_runner.py`

Extend `observe` action modes:

- `mode: "start"`
- `mode: "collect"`
- keep the existing one-shot behavior as `mode: "window"` or default compatibility behavior

Suggested flow shape:

```json
{
  "id": "start_observe_enemy_hit",
  "action": "observe",
  "mode": "start",
  "target": {"hint": "node_name:Enemy"},
  "event": {"kind": "signal_emitted", "signal_name": "hit_taken"},
  "windowMs": 800,
  "evidenceKey": "enemy_hit_signal"
}
```

```json
{
  "id": "collect_observe_enemy_hit",
  "action": "observe",
  "mode": "collect",
  "evidenceRef": "enemy_hit_signal"
}
```

Flow insertion pattern:

1. start observer
2. trigger action
3. collect observer
4. sample visible state
5. run evidence-backed checks

### Acceptance

A real `play_mode` validation flow proves:

- observer starts before the trigger
- event happens during or immediately after the trigger
- collected evidence includes event count and timestamps
- `check` can reference the evidence id

Add a new flow:

- `v2/flows/runtime_evidence_observe_flow.json`

## Phase 3: Repro Flow Uses Model Evidence Steps

### Code Changes

Modify:

- `v2/mcp_core/bug_repro_flow.py`
- `v2/mcp_core/bug_checks.py`
- `v2/mcp_core/bug_repro_execution.py`

Required behavior:

- insert model evidence steps by phase:
  - `pre_trigger`
  - `trigger_window`
  - `post_trigger`
  - `final_check`
- if `trigger_window` has an observer, materialize it as start observer -> trigger -> collect observer
- preserve existing base-flow reuse
- preserve existing assertion-derived wait/check steps
- mark which flow steps came from the model evidence plan

New output fields:

- `evidence_step_coverage`
- `model_planned_step_ids`
- `evidence_refs_required`
- `evidence_refs_produced`

### Acceptance

Given a model evidence plan, `plan_bug_repro_flow` returns a candidate flow containing:

- base setup steps
- model requested sample/observe steps
- evidence-backed checks
- existing `closeProject`

No fixed bug kind is required.

## Phase 4: Runtime Evidence In Fix Planning

### Code Changes

Modify:

- `v2/mcp_core/bug_fix_planning.py`
- `v2/mcp_core/bug_observation.py`
- `v2/tests/test_bug_fix_planning.py`
- `v2/tests/test_bug_observation.py`

Required behavior:

- `_evidence_summary` includes:
  - `runtime_evidence_summary`
  - failed evidence refs
  - inconclusive evidence refs
  - sample values relevant to failed checks
  - event counts relevant to failed checks
- `_candidate_files_from_observation` can rank files using:
  - failed check target hints
  - evidence target node path
  - related scene/script artifacts
  - runtime diagnostics
- `fix_goals` are based on failed evidence shape, not fixed bug categories

Example goal shapes:

- "make the target runtime property change during the observed post-trigger window"
- "make the expected event occur during the trigger window"
- "make the target runtime property return to its baseline after the observed window"

### Acceptance

For a repro artifact with runtime evidence:

- `plan_bug_fix` returns evidence-backed `fix_goals`
- `candidate_files` include reasons that mention concrete evidence refs or failed check ids
- `acceptance_checks` preserve the evidence-backed checks needed after edit

Current status:

- implemented for runtime evidence summaries, compact records, evidence refs, and evidence-backed acceptance checks
- deeper source-level ranking from concrete runtime node paths still needs follow-up work

## Phase 5: Bounded Model Edit Proposal Contract

### Code Changes

Add a new module:

- `v2/mcp_core/bug_fix_proposal.py`

Modify:

- `v2/mcp_core/bug_fix_application.py`
- `v2/mcp_core/server.py`
- `v2/mcp_core/tool_dispatch.py`
- `v2/tests/test_bug_fix_application.py`

New input args:

- `--fix-proposal-json`
- `--fix-proposal-file`

Proposal contract:

```json
{
  "candidate_file": "res://scripts/enemy.gd",
  "reason": "failed evidence enemy_modulate_after_hit shows modulate did not change after hit trigger",
  "edits": [
    {
      "kind": "replace_text",
      "find": "func take_damage(amount):",
      "insert_after": "\n\tflash_hit_feedback()"
    }
  ],
  "acceptance_check_ids": ["postcondition_check_0_enemy_modulate_changed"]
}
```

Allowed edit kinds for the first implementation:

- `replace_text`
- `insert_after`
- `insert_before`

Safeguards:

- only edit files listed in `plan_bug_fix.candidate_files`
- only edit `.gd` and `.tscn` initially
- reject if `find` text is absent or appears more than once
- persist the proposal before applying it
- persist applied change summary after applying it

Artifact files:

- `pointer_gpf/tmp/last_bug_fix_proposal.json`
- `pointer_gpf/tmp/last_bug_fix_application.json`

### Acceptance

`apply_bug_fix` no longer needs a fixed cause kind to apply a bounded proposal.

It can return:

- `fix_applied`
- `fix_not_ready`
- `fix_proposal_rejected`
- `fix_not_supported`

## Phase 6: Top-Level Explicit Repair Workflow

### Code Changes

Add a new tool:

- `repair_reported_bug`

Modify:

- `v2/mcp_core/server.py`
- `v2/mcp_core/tool_dispatch.py`
- `v2/mcp_core/request_layer.py`
- `v2/tests/test_server.py`
- `v2/tests/test_tool_dispatch.py`
- `v2/tests/test_request_layer.py`

Execution order:

1. `collect_bug_report`
2. `analyze_bug_report`
3. `observe_bug_context`
4. model supplies or selects an evidence plan
5. `plan_bug_repro_flow`
6. `run_bug_repro_flow`
7. `plan_bug_fix`
8. model supplies bounded fix proposal
9. `apply_bug_fix`
10. `rerun_bug_repro_flow`
11. `run_bug_fix_regression`
12. `verify_bug_fix`

Important execution rule:

- if no model evidence plan or no fix proposal is supplied, the workflow must stop with a clear `blocking_point` and the exact next tool/action needed
- do not silently invent code edits inside the deterministic MCP layer

### Acceptance

The workflow can return:

- `awaiting_model_evidence_plan`
- `bug_reproduced_awaiting_fix_proposal`
- `fix_applied_awaiting_verification`
- `fixed_and_verified`
- `blocked`

Every non-final status must include:

- `blocking_point`
- `next_action`
- `artifact_files`

## Phase 7: Real Validation Round For Behavior Bugs

### Code Changes

Extend validation tooling only after the generic workflow exists:

- `v2/mcp_core/test_project_bug_seed.py`
- `v2/mcp_core/test_project_bug_case.py`
- `v2/mcp_core/test_project_bug_restore.py`

Add one real behavior validation case:

- hit event is reachable
- visual feedback does not happen
- expected evidence is a property, animation, shader parameter, or signal event

This validation case must not become the product implementation.
It exists to prove the generic workflow.

Required round files:

- baseline manifest
- bug injection plan
- bug case
- restore plan
- repro result
- fix plan
- fix proposal
- fix application result
- rerun verification
- regression result

### Acceptance

The seeded behavior bug can be:

1. reproduced in real `play_mode`
2. explained by runtime evidence
3. fixed through bounded proposal application
4. verified by rerun
5. checked by regression
6. restored to baseline after validation

## Verification Plan

Run after each implementation phase:

```powershell
python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"
```

Run after runtime bridge changes:

```powershell
python -m v2.mcp_core.server --tool sync_godot_plugin --project-root D:\AI\pointer_gpf_testgame
& 'D:/GODOT/Godot_v4.6.1-stable_win64.exe/Godot_v4.6.1-stable_win64.exe' --headless --path D:\AI\pointer_gpf_testgame --quit
```

Run after `sample` or `observe` behavior changes:

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_sample_flow.json
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_observe_flow.json
```

Run before claiming the target is implemented:

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame
```

## Expected User Effect After This Plan Is Implemented

After this plan is implemented, a user should be able to install GPF in a new project and say:

```text
敌人在受击之后不会按照预期闪烁一次红色，帮我自动修复这个 bug
```

Expected system behavior:

1. GPF extracts the bug report and expected behavior.
2. If the trigger is unclear, GPF asks one bounded follow-up question.
3. The model inspects project evidence through GPF tools and chooses what runtime evidence to collect.
4. GPF runs a real `play_mode` repro flow.
5. GPF records evidence such as:
   - whether the hit signal or trigger happened
   - whether a color, shader parameter, or animation changed
   - whether the visual state returned to baseline
6. If the bug is reproduced, `plan_bug_fix` returns candidate files and fix goals backed by evidence ids.
7. The model proposes a bounded edit only inside candidate files.
8. GPF applies that edit only if it passes validation rules.
9. GPF reruns the same repro flow.
10. GPF runs regression.
11. GPF reports `fixed_and_verified` only if rerun and regression both pass.

Practical effect:

- the user no longer needs to manually translate a natural-language bug report into CLI fields
- the user no longer needs to manually decide whether to inspect animation, shader, signal, scene, or script state first
- GPF can work on behavior bugs, not only scene transition and missing-node bugs
- failures produce a concrete `blocking_point`, `next_action`, and artifact files instead of a vague explanation
- the implementation remains model-controlled and generic, not a growing list of fixed bug categories

## Final Acceptance Standard

This plan is complete only when all of these are true:

1. model-provided evidence plans can be validated and materialized into repro flows
2. cross-step event observation can capture events that happen during trigger actions
3. repro artifacts persist sample and event evidence linked to failed checks
4. fix planning ranks candidate files using runtime evidence refs
5. `apply_bug_fix` can apply a bounded model proposal without requiring a fixed cause kind
6. a top-level explicit repair workflow can stop safely when the model still needs to provide evidence or edit input
7. a real behavior-bug validation round proves repro, evidence, fix, rerun, regression, and restore
