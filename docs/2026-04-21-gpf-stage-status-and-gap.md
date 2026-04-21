# 2026-04-21 GPF Stage Status And Gap

## Purpose

This document records the difference between:

- what GPF can already do in the current repository
- what this stage is expected to deliver before the bug-repair workflow can be called complete

This is a status record, not a design note.

## Current Stage Requirement

The current stage is expected to deliver one usable bug-repair workflow with these steps:

1. accept a bounded bug report
2. analyze the related project files
3. define explicit preconditions and postconditions
4. plan a reproducible flow
5. run that flow and classify the result correctly
6. plan a code fix from confirmed repro evidence
7. apply a limited code fix
8. rerun the same bug-focused flow after the fix
9. run regression after the bug-focused rerun passes

The important requirement is not "more features".
The important requirement is that the workflow stays understandable, testable, and consistent.

## Already Implemented

The repository already has these bug-focused tools on the CLI path:

- `collect_bug_report`
- `analyze_bug_report`
- `define_bug_assertions`
- `plan_bug_repro_flow`
- `run_bug_repro_flow`
- `plan_bug_fix`
- `apply_bug_fix`

The repository also already has these important behavior guarantees:

- `run_bug_repro_flow` now classifies by execution phase instead of by failed step name guessing
- `run_bug_repro_flow` writes `pointer_gpf/tmp/last_bug_repro_result.json`
- `plan_bug_fix` uses the persisted repro result instead of running a new repro internally
- planner logic has been reduced to base flow reuse, explicit trigger insertion, and explicit precondition/postcondition checks
- assertion generation has been reduced to `preconditions` and `postconditions`
- current-project Godot processes are cleaned up after test runs

## Not Yet Implemented

The current repository does **not** yet provide the full expected stage result.

Missing items:

1. a formal tool that reruns the same bug-focused flow after `apply_bug_fix`
2. a formal tool that runs regression after the bug-focused rerun succeeds
3. a single top-level verification workflow that chains:
   - apply fix
   - rerun the same bug-focused flow
   - run regression
4. broader fix strategies beyond the current small set
5. broader assertion kinds for state values, runtime errors, and non-scene state checks

## What Should Not Expand Right Now

The following areas should not expand again during this stage unless a real failing case forces them:

- planner-side heuristic growth for UI, scene, delay, and repeated-click guessing
- broad natural-language routing beyond bounded bug-report inputs
- more `basicflow` product features unrelated to the bug-repair workflow
- more isolation work unless it directly blocks the bug-repair workflow

## Current Difference

The current repository already has a reliable middle section:

- bug report
- analysis
- assertion generation
- repro planning
- repro classification
- fix planning

The current repository does **not** yet have the expected final section as a stable product workflow:

- rerun same bug-focused flow after the code change
- run regression after that rerun
- report one final verification result for the repair attempt

## Immediate Development Target

The next repository work should add these missing pieces in this order:

1. rerun the same bug-focused flow after a code change
2. run regression after the rerun passes
3. expose one verification tool that reports the full repair result

## Acceptance For This Stage

This stage can be considered complete only when:

1. a confirmed bug can be reproduced
2. a supported fix can be applied
3. the same bug-focused flow can be rerun after the fix
4. regression can be run after the rerun
5. the final result clearly says whether the repair succeeded
