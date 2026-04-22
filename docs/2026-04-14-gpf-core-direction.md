# 2026-04-14 GPF Core Direction

## Core Position

GPF should return to its core product meaning:

- a Godot gray-box testing tool
- a bug reproduction tool
- a bug fixing assistant

That means the next main development direction is no longer:

- continuing to expand `basicflow` as the primary product focus
- continuing to prioritize input isolation as the immediate mainline

Those areas still matter, but they should be treated as later TODO work unless they directly block the core product loop below.

## Core User Scenario

The target scenario is:

1. the user finds a bug in the running game
2. the user describes the bug in natural language
3. GPF analyzes likely causes and affected systems
4. GPF defines the expected correct state as explicit assertions
5. GPF designs or updates a test flow that can reach the bug
6. GPF runs the flow to confirm the bug can actually be reproduced
7. GPF applies a fix
8. GPF reruns the updated flow and assertion set to confirm the bug is gone

This loop is the product center.

## What GPF Must Eventually Do In This Loop

### 1. Bug Intake

GPF should accept a bounded natural-language bug report such as:

- what the user did
- what happened
- what should have happened
- where in the game it happened

The system does not need open-ended NL coverage for everything.
It does need a reliable way to collect bug-focused input.

### 2. Cause Analysis

After receiving the bug report, GPF should inspect:

- relevant scenes
- related scripts
- current project flow path
- existing assertions or generated flow assumptions

The goal is not to guess endlessly.
The goal is to produce a small set of plausible causes and affected checkpoints.

### 3. Correct-State Assertion

GPF should convert "bug does not exist" into explicit testable assertions.

Examples:

- a node should become visible
- a button should stay enabled
- a scene transition should happen
- player state should not change unexpectedly
- an error signal or runtime error should not appear

This is critical because "fix the bug" is too vague without a machine-checkable target.

### 4. Flow Design Or Update

GPF should create or update a flow that can:

- reach the bug location
- trigger the bug condition
- evaluate the correct-state assertion

This may reuse and mutate an existing project flow instead of always creating a new one from scratch.

### 5. Reproduction

Before any fix is accepted, GPF should prefer proving:

- the bug is actually reproducible now
- the chosen flow reaches the correct area
- the failure is visible in assertions or runtime evidence

### 6. Fix + Re-Verification

After the bug is reproduced:

- GPF edits the relevant project code
- reruns the bug-focused flow
- confirms the new assertion state passes
- updates the maintained flow if the path changed during the fix

## Current Priority Decision

Current priority should be:

1. define the bounded bug-report -> assertion -> repro -> fix loop
2. build the first tool / contract slices for that loop
3. keep the existing V2 runtime chain stable enough to support it

Current priority should not be:

1. making input isolation the immediate mainline
2. continuing to expand `basicflow` productization as the main focus

## Deferred TODO Areas

### TODO Later: Input Isolation

`input isolation` remains important, but it should be treated as a later-stage improvement unless it directly blocks the new bug repro loop.

Deferred areas include:

- stronger proof of host-input isolation
- more complete isolated-runtime guarantees
- broader isolation-specific regression scenarios

### TODO Later: Basicflow Expansion

`basicflow` is already useful enough for the current stage.
Further expansion should be treated as later TODO work unless the new bug loop directly depends on it.

Deferred areas include:

- richer project-specific target inference
- broader `basicflow` asset UX
- more `basicflow` convenience refinement beyond current working scope

## Immediate Follow-Up

The next implementation planning should focus on the first thin slice of:

- bug report intake
- likely-cause analysis
- explicit correct-state assertion generation
- bug-focused flow planning or flow patching
- reproduction-first verification

That should become the next main product document and implementation target.
