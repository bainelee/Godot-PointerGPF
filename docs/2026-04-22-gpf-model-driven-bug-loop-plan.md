# 2026-04-22 GPF Model-Driven Bug Loop Plan

## Purpose

This document updates the mainline direction after the real-bug round system is in place.

The repository should **not** continue treating "enumerate more bug kinds and add one fix branch for each" as the main product path.

The main product path should now become:

- let the language model decide how to inspect the project
- let the language model decide how to operate the game
- let the language model decide what to check
- let the language model decide what to change
- keep execution bounded through explicit runtime and code-edit primitives

Reference:

- [2026-04-14-gpf-core-direction.md](/D:/AI/pointer_gpf/docs/2026-04-14-gpf-core-direction.md)
- [2026-04-14-gpf-bug-intake-and-assertion-contract.md](/D:/AI/pointer_gpf/docs/2026-04-14-gpf-bug-intake-and-assertion-contract.md)
- [2026-04-22-gpf-real-bug-development-plan.md](/D:/AI/pointer_gpf/docs/2026-04-22-gpf-real-bug-development-plan.md)

## Core Decision

GPF should not aim for:

- complete coverage through a fixed bug taxonomy
- complete coverage through a fixed set of predesigned flow templates
- complete coverage through a fixed set of repair branches

That is not realistic.

GPF should aim for:

- model-driven bug investigation
- model-driven game-operation planning
- model-driven check planning
- model-driven fix planning
- explicit execution and verification boundaries

In short:

- reasoning should be open within the bug workflow
- execution should remain bounded and testable

## Product Shape

The correct product shape is:

- open-ended bug reasoning
- bounded execution primitives

This means:

- the model is responsible for deciding what to inspect, what to try, what to verify, and what to edit
- the runtime system is responsible for launching, clicking, waiting, checking, collecting diagnostics, persisting evidence, and rerunning verification
- the repository should keep explicit evidence artifacts so conclusions remain reviewable

This does **not** mean:

- bringing back an open-ended natural-language router for everything
- silently chaining arbitrary high-impact actions from vague user language
- replacing verification with model opinion

## Relationship To Current Repository State

The repository already has the two foundations needed for this direction.

### 1. Execution foundation already exists

The runtime path can already:

- launch projects
- enter `play_mode`
- run explicit actions such as `click`, `wait`, and `check`
- collect runtime diagnostics
- rerun bug-focused verification
- run regression
- restore the external test project after a development round

This means the repository already has the bounded execution layer that a model-driven bug workflow needs.

### 2. Real-bug validation foundation already exists

The repository now also has:

- baseline recording
- real bug injection
- bug-case files
- restore plans
- restore verification

This means the repository already has a stable harness for validating whether model-driven investigation and repair logic is actually improving.

## What Must Change In The Mainline

The current mainline should move away from:

- adding more bug kinds as the default next step
- adding more hard-coded fix branches as the default next step
- growing planner heuristics around a small fixed catalog

The current mainline should move toward:

- giving the model better project observation tools
- giving the model better runtime observation tools
- giving the model a way to generate executable checks
- giving the model a way to iteratively refine the action plan based on evidence

## Required Capability Layers

### Layer 1: Project And Runtime Observation

The model needs better structured evidence before it can reliably decide what to do.

Add or improve tools that can expose:

- relevant scenes, scripts, and node paths
- signal and callback relationships
- startup path and reachable scene path hints
- current runtime failure point
- current runtime diagnostics summary
- per-step execution evidence summary
- scene and node presence/absence after each action

The goal is:

- do not force the model to guess from only one bug sentence

### Layer 2: Model-Driven Bug Investigation Plan

The system should add a step that produces a compact machine-readable investigation plan.

The plan should answer:

- what game path should be attempted first
- which actions should be tried
- what evidence should be collected after each action
- what alternative action should be tried if the first attempt fails
- which assertions should distinguish "bug reproduced" from "path not reached"

The goal is:

- move from fixed repro templates to evidence-guided action planning

### Layer 3: Model-Generated Checks

The system should let the model propose checks using bounded runtime primitives.

Checks should still compile down to explicit executable forms such as:

- scene reached
- node exists
- node hidden
- node enabled
- runtime diagnostic absent/present
- script or resource state matches an expected condition

The goal is:

- the model chooses what to check
- the runtime layer still executes the check explicitly

### Layer 4: Model-Driven Fix Planning

After repro is confirmed, the model should propose:

- the most likely affected files
- the intended behavioral correction
- the minimal code or scene changes that should restore the correct state
- the same bug-focused rerun and regression steps required for acceptance

The goal is:

- stop treating `apply_bug_fix` as a growing list of prewritten bug-kind handlers
- start treating it as a bounded code-edit workflow driven by evidence and verified by rerun

### Layer 5: Real-Bug Rounds As Evaluation Harness

The real-bug round system remains necessary, but it should now be treated as:

- a validation harness
- a regression harness
- a development harness

It should not be treated as the product center by itself.

Its role is to answer:

- did the model choose a valid path
- did the model pick useful checks
- did the model make a defensible code change
- did the project restore cleanly after the round

## Immediate Planning Change

The next mainline after the current repository state should be:

1. strengthen structured project and runtime observation
2. add a model-driven bug investigation plan step
3. add model-generated executable checks
4. add a model-driven fix-planning step before code edits
5. keep real-bug rounds as the evaluation method for those changes

The next mainline should **not** be:

1. enumerate more fixed bug kinds by default
2. enumerate more fixed fix strategies by default
3. expand `basicflow` product features unless the bug workflow proves a concrete gap

## Suggested Implementation Order

### Step 1

Add better observation payloads around:

- project structure
- related scenes and scripts
- runtime diagnostics
- flow-step evidence

### Step 2

Add a dedicated investigation-plan entrypoint that returns:

- candidate game path
- candidate actions
- candidate checks
- fallback branches

### Step 3

Let the model output a bounded executable check set rather than only a small fixed assertion catalog.

### Step 4

Replace the current default "one bug kind -> one code branch" growth pattern with:

- evidence-backed fix proposal
- bounded edit application
- mandatory rerun
- mandatory regression

### Step 5

Measure all of the above through controlled real-bug rounds and restoration.

## Repository Rule Going Forward

When choosing the next bug-work item, prefer this question:

- does this change improve the model's ability to observe, plan, check, or repair within explicit boundaries

Do **not** prefer this question:

- does this add one more fixed bug category to a growing list

That list can still grow when a specific gap must be tested.
It should no longer define the main product direction.
