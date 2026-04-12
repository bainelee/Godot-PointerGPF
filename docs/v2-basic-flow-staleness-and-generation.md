# V2 Basic Flow Staleness And Generation

## Purpose

This document defines:

- when V2 should warn that an existing `basicflow` may be stale
- how first-time generation should ask the user questions
- what should happen when the user asks to run a baseline flow but no `basicflow` exists yet

Reference:

- [v2-basic-flow-contract.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-contract.md)
- [v2-basic-flow-asset-model.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-asset-model.md)

## Staleness Policy

The staleness detector should be intentionally conservative.

Decision:

- prefer false positives over false negatives
- prefer simple, explainable checks over precise but fragile inference

## Priority Order For Staleness Checks

When deciding whether an old `basicflow` may no longer be meaningful, V2 should check in this order:

1. files directly related to the current `basicflow`
2. broad project code/file change volume
3. startup scene or critical runtime path changes

This order should stay visible in both code and user-facing explanations.

## Expected Detection Style

The detector should be "dumb on purpose".

Meaning:

- if the related files changed, warn early
- if overall project shape changed a lot, warn early
- do not wait for a highly confident semantic proof before warning

The goal is to avoid quietly running an out-of-date baseline flow.

## Initial Staleness Inputs

Phase 2 should begin with these inputs only:

- current `related_files` from `basicflow.meta.json`
- current project file counts compared to `project_file_summary`
- current startup scene or equivalent launch-path reference

Do not begin with:

- deep AST comparison
- wide dependency graph recovery
- expensive full-project semantic search

## Run-Time Decision Outcomes

When the user asks to run `basicflow`, V2 should produce one of these outcomes:

1. current `basicflow` looks valid enough
2. current `basicflow` may be stale and needs user choice
3. `basicflow` asset pair does not exist yet

## If `basicflow` Looks Valid Enough

V2 should:

- briefly remind the user what the current flow covers
- run it without rewriting it

## If `basicflow` May Be Stale

V2 should not silently regenerate.

It should warn and offer these choices:

1. analyze what the old `basicflow` did and where it no longer matches the current project
2. regenerate `basicflow`
3. let the user describe project changes or give other requirements
4. run the old `basicflow` anyway

If the user chooses option 4 and the old flow fails:

- analyze the failure and mismatch first
- suggest regeneration
- do not auto-update the flow

## If `basicflow` Does Not Exist Yet

Default behavior:

1. inspect the project
2. ask the generation questions
3. generate the first `basicflow`

Do not default to:

- hard error only
- silent generation with no user questions

## First-Time Generation Questions

The initial generation prompt should stay short.

Decision:

- ask 3 questions

The wording should stay easy for a user to understand.

Required questions:

1. `当前游戏工程的主场景是否是游戏主流程的入口？`
   - if not, the user can add the real entry in the follow-up
2. `你认为应该被测试的游戏功能都有哪些？`
3. `测试是否需要保留截图证据？`

## Why These Questions Exist

### Main scene entry question

Purpose:

- avoid assuming the startup scene is always the intended gameplay entry
- let the user correct the flow target early

### Tested feature question

Purpose:

- anchor the baseline flow to what the user thinks is meaningful
- avoid generating a technically valid but product-irrelevant path

### Screenshot evidence question

Purpose:

- keep screenshots optional
- avoid slowing down the default baseline run when the user does not need evidence artifacts

## Immediate Implementation Consequence

Before implementing auto-regeneration, V2 should first add:

1. a stale-check function that returns explainable reasons
2. a first-time asset-missing path that enters question-first generation
3. a user-choice contract for "warn, then choose" rather than silent replacement

## Current Conservative Generation Heuristics

Current V2 generation keeps the project-specific inference intentionally narrow and explainable.

When the startup scene provides enough signals, generation now prefers:

1. a startup UI scene that contains a likely start/play button
2. a startup script that clearly switches to another scene
3. the root node of that target scene
4. an optional runtime anchor scene such as a HUD loaded by the target scene or its script

Current generated modes are:

- `button_to_scene_with_runtime_anchor`
  - wait for the detected button
  - click it
  - wait for the detected target scene root
  - check the detected runtime anchor node
- `button_to_scene_root`
  - wait for the detected button
  - click it
  - wait for the detected target scene root
  - re-check the target scene root as the final assertion
- `generic_runtime_probe`
  - fall back to the generic visible-click probe when the conservative signals above are missing

This keeps the inference broad enough to cover obvious menu-to-scene projects, while still staying simple enough to explain from the recorded `related_files`.
