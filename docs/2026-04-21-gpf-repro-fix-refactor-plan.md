# 2026-04-21 GPF Repro And Fix Loop Refactor Plan

## Purpose

This document replaces the recent "keep extending the planner until the loop feels smart enough" direction.

The new rule is:

- stop expanding heuristic layers around an unclear center
- refactor the center contract first
- remove code that exists only because the center contract was wrong

## Current Root Problem

The current loop already has these entrypoints:

- `collect_bug_report`
- `analyze_bug_report`
- `define_bug_assertions`
- `plan_bug_repro_flow`
- `run_bug_repro_flow`
- `plan_bug_fix`
- `apply_bug_fix`

But the middle of the loop is still structurally wrong:

1. `run_bug_repro_flow` classifies results by matching failed `step_id` against assertion-related steps.
2. `plan_bug_fix` reruns repro internally instead of consuming a confirmed repro artifact.
3. `plan_bug_repro_flow` currently mixes three responsibilities:
   - path planning
   - heuristic trigger patching
   - partial classification support

This creates two bad outcomes:

- `precondition failure` can be misread as `bug_reproduced`
- more planner heuristics make the code longer without making the loop more trustworthy

## Refactor Goal

The loop should become:

1. `collect_bug_report`
2. `analyze_bug_report`
3. `define_bug_contract`
4. `plan_minimal_repro_flow`
5. `run_repro_flow`
6. `plan_bug_fix`
7. `apply_bug_fix`
8. `rerun_same_repro_flow`
9. `run_regression`

The center rule is:

- fix planning must depend on a previously confirmed repro result
- fix planning must not trigger a new repro run on its own

## New Center Contract

### Repro Result Contract

`run_bug_repro_flow` should classify only by execution phase:

- `precondition_failed`
- `trigger_failed`
- `bug_reproduced`
- `bug_not_reproduced`
- `runtime_invalid`

### Phase Meaning

- `precondition_failed`
  the flow could not reach the required ready-to-trigger state

- `trigger_failed`
  the trigger interaction itself did not execute successfully

- `bug_reproduced`
  trigger execution happened, then a post-trigger bug assertion failed

- `bug_not_reproduced`
  trigger execution happened, and all covered post-trigger assertions passed

- `runtime_invalid`
  runtime or bridge behavior prevented valid classification

### Important Negative Rule

The following must never be classified as `bug_reproduced`:

- missing precondition node
- wait failure before the trigger
- runtime bridge stall before trigger execution

## Repro Artifact Rule

`run_bug_repro_flow` must persist a repro artifact under the project tmp directory.

Suggested file:

- `pointer_gpf/tmp/last_bug_repro_result.json`

That artifact becomes the only default input for `plan_bug_fix`.

## Planner Scope Rule

`plan_bug_repro_flow` is allowed to do only:

1. choose or clone a base flow
2. insert explicit trigger steps
3. insert explicit precondition and postcondition assertion steps

It should not keep growing broad heuristic coverage unless a proven case requires it.

## Assertion Scope Rule

`define_bug_assertions` should eventually be narrowed into:

- `preconditions`
- `postconditions`

It should avoid generating extra "maybe useful" assertions that only exist to compensate for weak repro classification.

## Phase Plan

### Phase 1: Lock The Repro Contract

Deliverables:

- explicit execution-phase contract in `plan_bug_repro_flow`
- phase-based classification in `run_bug_repro_flow`
- repro artifact persistence

Acceptance:

- a pre-trigger `wait_startbutton` failure is not `bug_reproduced`
- a post-trigger expected-state failure is `bug_reproduced`

### Phase 2: Stop Internal Repro Reruns In Fix Planning

Deliverables:

- `plan_bug_fix` loads the last confirmed repro artifact
- `plan_bug_fix` returns `fix_not_ready` when no valid repro artifact exists

Acceptance:

- `plan_bug_fix` does not call `run_bug_repro_flow`
- repeated calls to `plan_bug_fix` do not change the repro result

### Phase 3: Shrink Planner Heuristics

Deliverables:

- remove or simplify planner logic that only existed to patch over weak classification
- keep only trigger mappings with clear product value

Candidates for removal or simplification:

- indirect assertion coverage fallback logic
- planner-side UI checkpoint growth that is not required by a real failing case
- assertion synthesis that does not map directly to preconditions or postconditions

Acceptance:

- `bug_repro_flow.py` is materially shorter
- planner responsibility is clearly limited to flow planning

### Phase 4: Shrink Assertion Generation

Deliverables:

- split assertion output into preconditions and postconditions
- remove assertions that do not directly express bug-free state

Acceptance:

- assertion generation no longer tries to compensate for missing classifier discipline

## Cleanup Policy

Any code introduced during the recent iteration must be removed if:

- it exists only to work around old repro misclassification
- it duplicates classification logic inside the planner
- it makes the planner larger without improving the center contract

This cleanup is required work, not optional polish.

## Immediate Execution Order

This refactor should be executed in this order:

1. implement phase-based repro classification
2. persist repro artifact
3. change fix planning to consume that artifact
4. only then begin deleting heuristic overflow from the planner and assertion generator
