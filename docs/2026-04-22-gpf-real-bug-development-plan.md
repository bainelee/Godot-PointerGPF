# 2026-04-22 GPF Real Bug Development Plan

## Purpose

This document replaces the previous "continue refining the repair workflow directly against the current test project state" direction.

The new rule is:

- future repair-workflow development must use bugs that are actually present in the test project
- if the test project does not already contain the needed bug, create one intentionally
- always record the original state first
- always restore the test project after the development round ends

Reference:

- [2026-04-21-gpf-bug-seeding-and-restoration-rules.md](/D:/AI/pointer_gpf/docs/2026-04-21-gpf-bug-seeding-and-restoration-rules.md)

## Current Situation

The repository already has these repair-workflow tools:

- `collect_bug_report`
- `analyze_bug_report`
- `define_bug_assertions`
- `plan_bug_repro_flow`
- `run_bug_repro_flow`
- `rerun_bug_repro_flow`
- `plan_bug_fix`
- `apply_bug_fix`
- `run_bug_fix_regression`
- `verify_bug_fix`

But one critical part is still missing:

- there is no real implementation yet for recording baseline state, injecting bugs, and restoring the test project

That means the current workflow code is not enough by itself to validate repair behavior against stable, known bug scenarios.

## Main Problem To Fix

Without test-project bug-round management, the repair workflow can still be driven by:

- a bug description that no longer matches the current project
- a test project that was already repaired earlier
- a verification result that does not come from a known, intentionally controlled bug state

This is not acceptable for the next stage.

## Target Result

The next stage should produce a controlled repair-development workflow:

1. start a bug-development round
2. record the original test-project state
3. inject one or more real bugs into the test project
4. generate the bug case data from that injected bug
5. use the injected bug to develop and validate GPF
6. restore the test project
7. verify the restored state

## Phase 1: Bug Round State Management

### Deliverables

Add a dedicated module for test-project bug rounds.

Suggested file:

- `v2/mcp_core/test_project_bug_round.py`

Suggested responsibilities:

- create a round id
- create `pointer_gpf/tmp/bug_dev_rounds/<round_id>/`
- write `baseline_manifest.json`
- copy original file contents into `baseline_files/`
- write `bug_injection_plan.json`
- write `restore_plan.json`
- restore files from the recorded baseline

### Acceptance

- the round module can record original file contents before bug injection
- the round module can restore those files later
- the round directory contains enough data for a new conversation to understand what happened

## Phase 2: Real Bug Injection

### Deliverables

Add a focused bug-injection module.

Suggested file:

- `v2/mcp_core/test_project_bug_seed.py`

First supported injected bug types should stay small and stable:

1. break a button signal connection
2. remove or disable a scene transition call
3. break one visibility or state-toggle path

Each injected bug must:

- define which files it changes
- define how to restore those files
- define the bug report fields GPF should later use

### Acceptance

- at least two bug types can be injected into the test project
- each injected bug changes actual runtime behavior
- each injected bug can be restored

## Phase 3: Bug Case Materialization

### Deliverables

Add a small representation for a bug case that comes from the round system rather than only from free text.

Suggested file:

- `v2/mcp_core/test_project_bug_case.py`

Suggested contents:

- bug id
- round id
- injected bug kind
- affected files
- bug-report payload fields
- expected verification target

### Acceptance

- repro and repair tools can read the bug case file directly
- the bug case points to a real injected bug, not only a user sentence

## Phase 4: Bind Existing Repair Tools To Bug Rounds

### Deliverables

Update these tools so they can use a bug-round-based source of truth:

- `run_bug_repro_flow`
- `plan_bug_fix`
- `apply_bug_fix`
- `rerun_bug_repro_flow`
- `verify_bug_fix`

Required behavior:

- when a bug case file is provided, use it as the main source
- report the current `round_id`
- report whether the bug was injected or pre-existing

### Acceptance

- repair-workflow tools no longer depend only on ad hoc bug descriptions
- outputs clearly say which round and which bug case they belong to

## Phase 5: Restore And Final Verification

### Deliverables

Add final round-completion behavior:

1. restore the test project after the development round
2. rerun the required validation checks
3. write a final restore result

Suggested file:

- `v2/mcp_core/test_project_bug_restore.py`

### Acceptance

- after a round finishes, the test project returns to the recorded baseline
- restore verification is written to a durable file

## Execution Order

The required order is:

1. implement bug round state management
2. implement real bug injection
3. implement bug case materialization
4. bind the existing repair tools to bug rounds
5. implement restore and restore verification

Do not reverse this order.

## What Must Not Happen During This Work

Do not spend the next phase on:

- more planner heuristics
- more free-form bug phrase handling
- more basicflow product work
- more fix strategies before bug-round management exists

The next bottleneck is not more repair heuristics.
The next bottleneck is the lack of a controlled real-bug source and restore workflow.
