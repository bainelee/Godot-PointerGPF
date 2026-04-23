# 2026-04-23 GPF Generic Runtime Evidence Primitives Plan

## Purpose

This document defines the next implementation plan after the initial `bug_repair` request entry exists.

The target of this plan is:

- give the language model generic runtime evidence primitives
- let the language model decide what to inspect, what to sample, what to compare, and what to verify for the current bug report
- keep GPF focused on explicit MCP tools, explicit runtime actions, explicit evidence artifacts, and explicit verification

This plan is not for adding support for one named bug.
This plan is for adding generic runtime evidence capabilities that the model can use across many bug reports.

## Current Facts

Current implementation facts from the repository:

- [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd) currently supports `launchGame`, `delay`, `capture`, `click`, `wait`, `check`, `snapshot`, `closeProject`
- current `capture` support is narrow and metric-based
- current metric reads are limited to `rotation_y` and `global_rotation_y`
- current `check` behavior mainly evaluates one `hint` or one capture comparison
- [bug_checks.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_checks.py) currently compiles runtime checks from one `hint` field
- [bug_repro_execution.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repro_execution.py) persists pass/fail summaries, but not rich time-series evidence
- [bug_observation.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_observation.py) reads existing runtime diagnostics and latest repro summary, but it does not yet expose reusable runtime-evidence capability descriptions
- [flow_runner.py](/D:/AI/pointer_gpf/v2/mcp_core/flow_runner.py) already supports command-response execution and per-step event logging, so it can carry richer step payloads without changing the basic transport model

Update after implementation on 2026-04-23:

- Python-side `sample`, `observe`, and structured `check` contracts are implemented
- `runtime_bridge.gd` now implements generic `sample` and `observe` actions
- `check` can evaluate a generic `evidenceRef` against a bounded predicate
- `FlowRunner` now collects runtime evidence records from bridge responses and deduplicates them by evidence id
- `run_basic_flow_tool` exposes runtime evidence records and summaries in the successful result payload
- a real `play_mode` flow has verified `sample` plus `evidenceRef` check against the external test project
- a real `play_mode` flow has verified cross-step `observe` evidence that starts before a trigger and collects after it
- model evidence plans can now insert `sample`, `observe`, and evidence-backed `check` steps into `plan_bug_repro_flow`
- `plan_bug_fix` now receives runtime evidence summaries, compact evidence records, and evidence-backed acceptance checks

Current limitation:

- the model can already decide some checks
- the runtime layer now has generic state evidence primitives for bounded reads, samples, and event windows
- model generation of those structured checks from arbitrary bug reports still needs more implementation work
- behavior-bug validation still needs a seeded real bug that uses these primitives through `repair_reported_bug`

## Implementation Result On 2026-04-23

Implemented:

- [contracts.py](/D:/AI/pointer_gpf/v2/mcp_core/contracts.py) now accepts `sample` and `observe` flow actions.
- [bug_checks.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_checks.py) supports structured runtime checks with `check_type`, `metric`, `sample_plan`, `predicate`, `evidence_requirements`, and `evidence_ref`.
- [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd) implements generic `sample` and `observe` actions.
- `sample` can read node properties, shader parameters, animation state, node existence, and signal-connection existence over a bounded time window.
- `observe` can watch scene changes, animation started/finished events, and bounded signal emissions.
- `check` can evaluate an `evidenceRef` against bounded predicates such as `sample_count_at_least`, `event_count_at_least`, `not_equals`, `changed_from_baseline`, and `returned_to_baseline`.
- [flow_runner.py](/D:/AI/pointer_gpf/v2/mcp_core/flow_runner.py) collects bridge evidence records and deduplicates them by evidence id.
- [runtime_orchestration.py](/D:/AI/pointer_gpf/v2/mcp_core/runtime_orchestration.py) exposes runtime evidence records and summaries in `run_basic_flow_tool` results.
- [bug_repro_execution.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repro_execution.py) persists runtime evidence records and summaries when they are present in repro run results.
- [bug_observation.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_observation.py) exposes runtime evidence capabilities and the latest runtime evidence summary.
- [runtime_evidence_sample_flow.json](/D:/AI/pointer_gpf/v2/flows/runtime_evidence_sample_flow.json) verifies a real `sample` plus evidence-backed `check` path.
- [runtime_evidence_observe_flow.json](/D:/AI/pointer_gpf/v2/flows/runtime_evidence_observe_flow.json) verifies a real cross-step `observe` plus evidence-backed `check` path.

Verified:

- `python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"` returned `Ran 181 tests in 1.605s`, `OK`.
- `python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame` returned `ok: true`, including `v2_unit_tests`, `preflight_project`, `basic_interactive_flow`, `default_basicflow`, `basicflow_stale_override`, and `runtime_guards`.
- `python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_sample_flow.json` returned `ok: true`, `execution.status: passed`, `runtime_evidence_summary.record_count: 1`, and `project_close.status: verified`.
- Later verification after cross-step observe and repair workflow implementation:
  - `python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"` returned `Ran 199 tests in 1.790s`, `OK`.
  - `python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_observe_flow.json` returned `ok: true`, `execution.status: passed`, `runtime_evidence_summary.record_count: 1`, evidence id `scene_change_window`, and event scene `res://scenes/game_level.tscn`.
  - `python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame` returned `ok: true`, including `v2_unit_tests` with `Ran 97 tests`, `preflight_project`, `basic_interactive_flow`, `default_basicflow`, `basicflow_stale_override`, and `runtime_guards`.

Still not complete:

- the model does not yet reliably generate structured `sample` or `observe` steps from arbitrary natural-language bug reports.
- full behavior-bug validation still needs a seeded real bug that uses runtime evidence, bounded fix proposal, rerun, regression, and restore.

## Product Rule

The product rule for this plan is:

- the model decides bug reasoning
- GPF executes bounded runtime primitives

This means:

- do not add a runtime feature because one named bug example needs it
- add a runtime primitive only when it can help the model verify many bug reports
- the runtime layer should expose generic read, sample, compare, and event primitives
- the runtime layer should not embed a large offline bug taxonomy

## Main Goal

After this plan is implemented, the model should be able to do work such as:

1. read a bug report
2. inspect project files and runtime context
3. decide that some runtime evidence is needed
4. request property sampling, event observation, animation observation, or state comparison
5. get a persisted evidence artifact with concrete values and timestamps
6. use that artifact to choose the next check, next repro change, or next code edit

The important point is:

- GPF should not decide what the bug is through hard-coded categories
- GPF should provide the model with enough bounded actions to answer that question from project facts and runtime evidence

## Required Capability Groups

### 1. Generic Runtime Read Primitives

GPF needs a way to read runtime state from nodes without writing bug-specific logic.

Required read targets:

- node property by path such as `modulate`, `visible`, `text`, `frame`, `disabled`
- shader parameter by name
- animation player current animation and playback state
- node existence and node path resolution result
- signal connection existence

Required output:

- `target_resolved`
- `node_path`
- `value`
- `value_type`
- `read_source`
- `timestamp_ms`

Primary files:

- [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd)
- [flow_runner.py](/D:/AI/pointer_gpf/v2/mcp_core/flow_runner.py)

### 2. Generic Runtime Sampling Primitives

GPF needs time-window sampling instead of only one instant read.

Required sampling modes:

- sample property every N milliseconds for a bounded window
- sample shader parameter every N milliseconds for a bounded window
- sample animation state every N milliseconds for a bounded window
- sample node existence or visibility every N milliseconds for a bounded window

Required output:

- `sample_id`
- `sample_kind`
- `metric`
- `target`
- `window_ms`
- `interval_ms`
- ordered sample points with timestamp and value

Primary files:

- [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd)
- [bug_repro_execution.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repro_execution.py)

### 3. Generic Runtime Event Observation Primitives

GPF needs a way to observe events that happen during a window.

Required event types:

- signal emission
- animation started
- animation finished
- scene changed
- runtime diagnostic item written during the current run

Required output:

- `observer_id`
- `event_kind`
- `window_ms`
- ordered event records with timestamp and payload

Primary files:

- [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd)
- [bug_repro_execution.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repro_execution.py)

### 4. Generic Comparison Primitives

The runtime layer should compare evidence without assuming one bug category.

Required comparison forms:

- value equals expected
- value differs from baseline
- value changes within a window
- value restores within a window
- event happened at least once
- event did not happen
- sampled value matches one predicate during a window

Required predicate support:

- equals
- not_equals
- greater_than
- less_than
- contains
- within_tolerance
- changed_from_baseline
- returned_to_baseline

Primary files:

- [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd)
- [bug_checks.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_checks.py)

### 5. Generic Check Contract

Current checks are still centered on one `hint` string.
That is too narrow for model-controlled runtime evidence work.

The next check contract should support:

- `check_type`
- `target`
- `metric`
- `sample_plan`
- `predicate`
- `expected`
- `evidence_requirements`

Suggested check types:

- `node_exists`
- `node_property_equals`
- `node_property_changes_within_window`
- `node_property_returns_to_baseline`
- `shader_param_changes_within_window`
- `signal_emitted`
- `animation_state_matches`
- `runtime_diagnostic_absent`
- `runtime_diagnostic_present`

Important rule:

- these are bounded executable check forms
- they are not product-level bug categories

Primary files:

- [bug_checks.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_checks.py)
- [bug_repro_flow.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repro_flow.py)

### 6. Generic Evidence Artifact Contract

The runtime layer needs a richer persisted artifact so the model can reason from concrete evidence after the run.

Add a new artifact section to repro results:

- `runtime_evidence_catalog`
- `runtime_evidence_records`
- `runtime_evidence_summary`

Suggested record types:

- `read_result`
- `sample_result`
- `event_observer_result`
- `comparison_result`

Suggested summary fields:

- `record_count`
- `failed_evidence_ids`
- `inconclusive_evidence_ids`
- `evidence_by_check_id`

Primary files:

- [bug_repro_execution.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repro_execution.py)
- [bug_observation.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_observation.py)

## File-Level Implementation Plan

### A. `v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd`

Required changes:

- add generic runtime read helpers for property, shader param, animation state, and signal connection existence
- add `sample` action for bounded time-window sampling
- add `observe` action for bounded event observation
- keep current `click`, `wait`, `check`, `capture` behavior working during transition
- add an internal evidence store for the current `run_id`
- include evidence ids and evidence payloads in responses

Suggested new internal helpers:

- `_read_runtime_target`
- `_sample_runtime_target`
- `_observe_runtime_events`
- `_compare_evidence_against_predicate`
- `_serialize_variant_value`

Compatibility rule:

- keep existing `capture` support until Python-side callers are migrated
- `capture` may later become one narrow wrapper around the new generic read or sample contract

### B. `v2/mcp_core/flow_runner.py`

Required changes:

- allow richer step payloads for `sample` and `observe`
- persist bridge response details into step events when they contain evidence ids or evidence payloads
- keep the transport format stable: one command file, one response file

Suggested additions:

- per-step `bridge_details`
- optional `runtime_evidence_refs`

### C. `v2/mcp_core/bug_checks.py`

Required changes:

- support structured runtime checks instead of only `hint`
- compile assertions into explicit generic check contracts
- support step mapping for `sample` and `observe` actions in addition to `check` and `wait`
- summarize evidence-backed failures with `check_type`, `predicate`, and `evidence_ref`

Suggested internal refactor:

- keep current `hint` path as compatibility fallback
- add `_compile_structured_runtime_check`
- add `_check_signature_for_step_mapping`

### D. `v2/mcp_core/bug_repro_flow.py`

Required changes:

- allow candidate steps to include `sample` and `observe`
- insert model-requested evidence steps before trigger, around trigger, or after trigger
- keep current base-flow reuse logic

Suggested additions:

- `pre_trigger_evidence_steps`
- `trigger_window_evidence_steps`
- `post_trigger_evidence_steps`

### E. `v2/mcp_core/bug_repro_execution.py`

Required changes:

- collect evidence records from step results
- persist `runtime_evidence_catalog`, `runtime_evidence_records`, and `runtime_evidence_summary`
- include evidence refs in `check_results`
- keep current repro status classification unchanged unless evidence shows a clearer failure point

Suggested internal helpers:

- `_collect_runtime_evidence`
- `_summarize_runtime_evidence`
- `_attach_evidence_to_check_results`

### F. `v2/mcp_core/bug_observation.py`

Required changes:

- expose the latest runtime evidence summary alongside diagnostics and latest repro summary
- expose supported runtime evidence primitives so the model can choose them intentionally

Suggested output additions:

- `runtime_evidence_capabilities`
- `latest_runtime_evidence_summary`

## Suggested Data Contract Changes

### Runtime Step Contract

Suggested new actions:

- `sample`
- `observe`

Suggested `sample` step shape:

```json
{
  "id": "sample_enemy_modulate",
  "action": "sample",
  "target": {"hint": "node_name:Enemy"},
  "metric": {
    "kind": "node_property",
    "property_path": "modulate"
  },
  "windowMs": 400,
  "intervalMs": 50,
  "evidenceKey": "enemy_modulate_window"
}
```

Suggested `observe` step shape:

```json
{
  "id": "observe_enemy_hit_signal",
  "action": "observe",
  "target": {"hint": "node_name:Enemy"},
  "event": {
    "kind": "signal_emitted",
    "signal_name": "hit_taken"
  },
  "windowMs": 400,
  "evidenceKey": "enemy_hit_signal_window"
}
```

Suggested structured `check` step shape:

```json
{
  "id": "check_enemy_modulate_changed",
  "action": "check",
  "checkType": "node_property_changes_within_window",
  "evidenceRef": "enemy_modulate_window",
  "predicate": {
    "operator": "not_equals",
    "compareTo": "baseline_first_sample"
  }
}
```

### Repro Artifact Additions

Suggested new repro artifact fields:

- `runtime_evidence_catalog`
- `runtime_evidence_records`
- `runtime_evidence_summary`

The current fields that should remain:

- `executable_checks`
- `check_results`
- `check_summary`
- `failed_phase`
- `status`

## Implementation Order

### Phase 1: Define Generic Contracts

Change:

- write the new runtime step and evidence artifact contracts into code and tests before broad behavior changes

Files:

- `v2/mcp_core/bug_checks.py`
- `v2/mcp_core/bug_repro_execution.py`
- test files for these modules

Acceptance:

- the Python side can represent generic `sample`, `observe`, and structured `check` payloads without requiring one named bug type

Current status:

- implemented
- verified by unit tests

### Phase 2: Extend Runtime Bridge

Change:

- add generic read, sample, and observe support to the Godot runtime bridge

Files:

- `v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd`

Acceptance:

- the bridge can execute one sample request and one observe request and return evidence payloads with timestamps

Current status:

- `sample` is implemented and verified in real `play_mode`
- `observe` is implemented and verified in real `play_mode`, including cross-step start/collect behavior

### Phase 3: Persist Evidence In Repro Artifacts

Change:

- collect runtime evidence from step responses and write it into durable repro artifacts

Files:

- `v2/mcp_core/flow_runner.py`
- `v2/mcp_core/bug_repro_execution.py`

Acceptance:

- a repro artifact includes both check summary and raw runtime evidence records

Current status:

- implemented for flow reports and `run_basic_flow_tool` result payloads
- implemented for bug repro artifacts when runtime evidence records are present in the raw run result

### Phase 4: Let The Model Choose Structured Checks

Change:

- move assertion compilation from one `hint` string toward structured check forms

Files:

- `v2/mcp_core/bug_checks.py`
- `v2/mcp_core/bug_repro_flow.py`

Acceptance:

- the model can choose a property-window or event-based check without adding a new bug-specific execution branch

### Phase 5: Expose Evidence To Observation And Fix Planning

Change:

- expose latest runtime evidence summaries in bug observation and bug fix planning inputs

Files:

- `v2/mcp_core/bug_observation.py`
- `v2/mcp_core/bug_fix_planning.py`

Acceptance:

- the model receives recent runtime evidence summaries when planning the next repro step or fix step

## Test Plan

### Unit Tests

Add or update tests for:

- [test_flow_runner.py](/D:/AI/pointer_gpf/v2/tests/test_flow_runner.py)
- [test_bug_repro_execution.py](/D:/AI/pointer_gpf/v2/tests/test_bug_repro_execution.py)
- [test_bug_observation.py](/D:/AI/pointer_gpf/v2/tests/test_bug_observation.py)
- add a new runtime-bridge focused test file if current coverage becomes too large

Required unit-test cases:

- structured sample step is accepted by flow loading
- runtime evidence records are persisted into repro artifacts
- check summary can reference evidence ids
- observation payload includes latest runtime evidence summary

### Real Validation

Use real bug rounds only as validation cases.
Do not treat them as the product design itself.

Validation cases should prove that:

- the model can request a generic time-window sample
- the model can request a generic signal or animation observation
- the resulting evidence artifact is sufficient to support a fix plan

## Acceptance Standard

This plan should be considered complete only when all of the following are true:

1. the model can request generic runtime evidence primitives without a bug-specific execution branch
2. the runtime bridge can return timestamped evidence for reads, samples, and event observations
3. repro artifacts persist that evidence in a durable structure
4. bug checks can point to evidence ids instead of only one `hint`
5. bug observation can expose recent runtime evidence summaries back to the model
6. the same primitives are usable across different bug reports without adding a new runtime feature for each report

## Repository Rule For This Work

When choosing the next code change in this area, prefer this question:

- does this change give the model a better generic runtime evidence primitive

Do not prefer this question:

- does this change help one named bug example by itself

The runtime layer should become more general.
The model should stay responsible for deciding what a specific bug likely is.
