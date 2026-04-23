# 2026-04-22 GPF New-Project Natural-Language Bug Auto-Fix Plan

## Purpose

This document records one real product target from actual user demand and turns it into the next complete implementation plan.

Recorded user target:

- after installing GPF into a new Godot project, the user should be able to describe a real bug in natural language
- GPF should inspect the project, reproduce the bug in real `play_mode`, apply a bounded code or scene fix, rerun verification, and report one final result

Canonical example:

- user request: `敌人在受击之后不会按照预期闪烁一次红色，帮我自动修复这个 bug`

This document exists because that scenario is closer to the real product goal than more `basicflow` expansion or more fixed bug handlers.

Important rule:

- the example above is only a real-world acceptance case
- it must not be turned into a dedicated bug category, dedicated planner branch, or dedicated repair feature
- GPF is an AI MCP system, not an offline bug taxonomy tool
- the language model should decide what the bug likely is, where it likely comes from, what should be checked, and what should be changed
- GPF should provide bounded project observation, runtime execution, code or scene editing, and verification primitives for the model to use

## Recorded Real-World Scenario

The intended end-state user experience is:

1. the user installs GPF into a new project
2. the user gives one explicit bug-fix request in natural language
3. GPF turns that request into a structured bug report
4. GPF asks only a small bounded follow-up question when a critical field is missing
5. GPF inspects scenes, scripts, runtime diagnostics, and recent runtime evidence
6. GPF plans a repro flow and executable checks for that exact bug
7. GPF runs the repro in real `play_mode`
8. GPF uses the repro evidence to decide which files to change
9. GPF applies a minimal code or scene edit
10. GPF reruns the same bug-focused flow
11. GPF runs regression
12. GPF reports either `fixed and verified`, or one concrete `blocking_point` plus one explicit `next_action`

The canonical scenario in this plan is not limited to UI scene changes.
It includes behavior bugs such as:

- hit feedback missing
- enemy state transition wrong
- animation or shader response missing
- runtime event occurred but visible result did not happen

## Why This Scenario Matters

This scenario matters for the user because:

- it matches the first real expectation after installation: "I found a bug in my own project, help me fix it"
- it reduces the amount of manual investigation the user must do before getting a useful answer
- it makes GPF useful on a project that does not look like the repository test game

This scenario matters for continued GPF development because:

- it forces the product to handle behavior bugs instead of only startup-path bugs
- it requires project observation, runtime evidence, repair planning, edit execution, and verification to work together
- it gives a concrete standard for deciding whether the next change helps the real product or only adds another narrow heuristic

## Current Facts

The repository already has bug-report, repro, evidence, and fix-plan pieces.
The repository now also has the first implementation of the generic workflow pieces required by this target.

Already implemented:

- the current natural-language request layer routes explicit bug repair requests to `repair_reported_bug`
- the user command guide documents bug repair requests and the required model evidence / fix proposal inputs
- runtime evidence primitives now include `sample`, cross-step `observe`, and evidence-backed `check`
- repro artifacts can persist runtime evidence records and summaries when those records are present
- `plan_bug_repro_flow` can materialize model evidence plans into a candidate repro flow
- `plan_bug_fix` includes runtime evidence summaries, compact evidence records, evidence refs, and evidence-backed acceptance checks
- `apply_bug_fix` can apply a bounded model fix proposal inside candidate files without requiring a fixed strategy kind
- `repair_reported_bug` now runs the explicit sequence and stops safely when the model still needs to supply an evidence plan or fix proposal

Current remaining blocking facts:

- the model does not yet reliably generate high-quality evidence plans from arbitrary natural-language bug reports without an external model step
- the model still has to generate a valid bounded fix proposal; GPF validates and applies it but does not invent arbitrary code edits inside the deterministic MCP layer
- current real-bug rounds do not yet include a behavior bug that matches hit-feedback or animation-feedback failures

Concrete consequence:

- a bug like "enemy should flash red once after hit" can now enter `repair_reported_bug` and safely request the next model input
- it should not yet be claimed as fully auto-fixed until a real seeded behavior-bug round proves repro, runtime evidence, bounded fix proposal, rerun, regression, and restore

## Product Rules For This Target

The target product behavior should remain explicit and reviewable.

Required boundaries:

- GPF should only enter the full repair workflow when the user makes an explicit repair request
- GPF should not silently edit files from a vague request such as "look around and do whatever you think is best"
- GPF may ask one small bounded follow-up question when the repro trigger or expected behavior is too incomplete to act on
- all code or scene edits must be tied to persisted repro evidence and persisted candidate-file reasoning
- final success claims must come from rerun plus regression results, not from model opinion

This means the desired product shape is:

- open bug reasoning
- bounded execution
- bounded editing
- mandatory verification

This also means:

- do not build the next stage around a growing bug taxonomy
- do not add one product feature for each named bug example
- do not force the product to classify bugs through an offline ruleset before the model can reason about them

## Required Capability Layers

### Layer 1: Explicit Bug-Repair User Request Entry

The request layer must support user requests such as:

- `帮我修复这个 bug：敌人在受击之后不会按预期闪红一次`
- `这个项目里敌人受击没有红闪，请自动排查并修复`
- `修这个 bug，受击后应该闪红一次，但现在没有`

Required changes:

- implemented in `v2/mcp_core/request_layer.py` through routing to `repair_reported_bug`
- implemented in `v2/mcp_core/tool_dispatch.py` and `v2/mcp_core/server.py`
- documented in [v2-how-to-command-gpf.md](/D:/AI/pointer_gpf/docs/v2-how-to-command-gpf.md)

Required output shape:

- structured bug summary
- extracted trigger description
- extracted expected behavior
- extracted likely target area if the request names one
- `missing_fields` only when execution truly cannot continue

### Layer 2: Better Static Observation For Model-Guided Bug Work

The observation layer must expose generic project evidence that the model can use for many different bug types.

The goal is not to recognize one named bug category.
The goal is to expose enough evidence for the model to reason about the reported bug.

Examples of useful generic evidence:

- likely damage-entry methods such as `take_damage`, `apply_hit`, `hurt`, `_on_hit`
- likely visual feedback paths such as `AnimationPlayer`, `Tween`, `modulate`, `self_modulate`, shader params, materials, sprites, and effects nodes
- signal connections that link hit events to feedback methods
- relevant nodes and scripts around the reported target

Primary implementation area:

- extend `v2/mcp_core/bug_observation.py`
- add helper modules when the observation payload becomes too large for one file

Required observation output:

- candidate nodes
- candidate scripts
- candidate scene files
- likely trigger methods
- likely feedback methods
- likely visual-state properties to sample at runtime

### Layer 3: Runtime Evidence For Model-Chosen State Checks

The current runtime path needs richer generic evidence so the model can define and verify bug-specific checks.

For example, when the model decides a reported bug depends on time-based visible state, GPF must be able to confirm facts such as:

- the enemy actually received the hit trigger
- the expected sprite or material changed color or shader state
- the change happened within a bounded time window
- the color returned to the normal state after the flash

Required runtime primitives:

- sample node property over time
- sample shader parameter over time
- record animation start and finish events
- record signal emissions tied to the trigger path
- optionally capture frame or screenshot evidence when property sampling is insufficient

Primary implementation area:

- `v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd`
- runtime action and check execution code under `v2/mcp_core/`

Required artifact additions:

- property-sample timeline
- event timeline
- optional frame-capture metadata
- explicit mapping from each check to the runtime evidence that passed or failed

These primitives must remain generic.
They should be callable by the model for any bug where that kind of evidence is relevant.

### Layer 4: Model-Driven Investigation

The investigation step must be controlled by the model instead of a fixed bug catalog.

When the model reads the bug report and project evidence, the investigation plan should decide:

- how to reach the enemy
- how to trigger damage
- what evidence to collect before the hit
- what evidence to collect immediately after the hit
- what evidence to collect after the flash window should have ended
- what alternative path to try if the first trigger does not reach the enemy

Primary implementation area:

- `v2/mcp_core/plan_bug_investigation`
- `v2/mcp_core/bug_repro_flow.py`
- `v2/mcp_core/bug_checks.py`
- `v2/mcp_core/bug_repro_execution.py`

Required new check shapes:

- property changed to expected value within time window
- property restored within time window
- animation played
- shader parameter toggled
- signal emitted
- method side effect observed through runtime state

The important rule is:

- these are generic bounded check forms
- they are not per-bug product features
- the model chooses which checks to use for the current report

### Layer 5: Evidence-Backed Fix Planning

The fix planner must move from "suspected cause category" toward "change proposal backed by evidence".

Required fix-plan output:

- candidate files ordered by evidence strength
- intended behavior correction in plain language
- explicit acceptance checks reused from repro evidence
- suggested minimal edit type such as `add missing feedback trigger call`
- suggested minimal edit type such as `restore missing animation or tween start`
- suggested minimal edit type such as `restore missing color reset`
- suggested minimal edit type such as `fix broken node path or shader parameter name`

Primary implementation area:

- `v2/mcp_core/bug_fix_planning.py`

The planner should explicitly say when the main uncertainty is:

- trigger path not reached
- visual state not changed
- visual state changed but did not reset
- feedback asset exists but is not invoked

### Layer 6: Bounded General Edit Workflow

The main missing piece is not another fixed bug branch.
The main missing piece is a broader bounded edit workflow.

Required behavior:

- allow the model to propose edits only inside the evidence-ranked candidate files
- support both `.gd` and `.tscn` edits where needed
- store the proposed change summary before applying it
- apply the minimal patch that should satisfy the failed acceptance checks
- reject edits when the plan cannot point to a defensible candidate file set

Primary implementation area:

- [bug_fix_proposal.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_fix_proposal.py)
- [bug_fix_application.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_fix_application.py)

Required safeguards:

- persist the fix proposal before edit
- persist the applied patch summary after edit
- keep the rerun and regression requirements mandatory
- return `fix_not_ready` or `fix_not_supported` with a concrete reason when evidence is not good enough

### Layer 7: One Top-Level Bug Repair Workflow

After the layers above exist, GPF should expose one bounded top-level workflow for explicit repair requests.

Suggested tool shape:

- `repair_reported_bug`

Current status:

- implemented in [bug_repair_workflow.py](/D:/AI/pointer_gpf/v2/mcp_core/bug_repair_workflow.py)
- exposed through `server.py`, `tool_dispatch.py`, and `request_layer.py`
- smoke tested with the canonical enemy red-flash request; it returned `status: awaiting_model_evidence_plan`, `blocking_point: repair_reported_bug requires an accepted model evidence plan before running repro`, and `next_action: provide_evidence_plan_json_or_file`

Suggested execution order:

1. collect bug report
2. analyze bug report
3. observe project and runtime context
4. plan bug investigation
5. run repro in real `play_mode`
6. plan fix from evidence
7. apply fix
8. rerun the same repro
9. run regression
10. emit one final verification result

The final payload should always include:

- `status`
- `artifact_files`
- `applied_changes`
- `verification_summary`
- `blocking_point`
- `next_action`

### Layer 8: Validation With Real Project Bugs

The real-bug round system must validate this scenario with actual project bugs, not only UI path bugs.

Add at least one controlled validation path that matches a real behavior bug such as:

- enemy receives hit but red flash never starts

This is a validation case, not a product category.

Recommended validation cases for the external test project:

- missing hit-feedback method call
- broken `AnimationPlayer` animation name
- wrong sprite or shader node path
- color changes to red but never resets
- shader parameter name mismatch

Validation requirement:

- each bug must be a real project bug
- each bug must be recordable through baseline/seed/restore files
- each bug must be repairable through the same public workflow being developed

## Suggested Implementation Order

### Phase 1: Record And Route Explicit Bug-Repair Requests

Implement:

- bug-repair request phrases
- structured extraction of bug sentence fields
- bounded follow-up for missing trigger or expected behavior details

Acceptance:

- a user request about a concrete bug is recognized as a repair request
- GPF can return a machine-readable intake payload without requiring CLI-only arguments

Current status:

- implemented
- routed to `repair_reported_bug`
- documented in [v2-how-to-command-gpf.md](/D:/AI/pointer_gpf/docs/v2-how-to-command-gpf.md)

### Phase 2: Add Runtime Evidence For Behavior Bugs

Implement:

- property timeline sampling
- animation and signal evidence
- runtime artifact persistence for time-window checks

Acceptance:

- a test can prove whether a sprite or shader changed state during a bounded time window

Current status:

- generic `sample`, cross-step `observe`, and evidence-backed `check` are implemented
- sample and observe validation flows passed in real `play_mode`

### Phase 3: Add Investigation And Repro Support For Behavior Bugs

Implement:

- behavior-bug investigation planning
- time-window executable checks
- bug-specific repro planning for hit-feedback style bugs

Acceptance:

- a seeded hit-feedback bug can be reproduced with explicit failed checks and persisted evidence
- the implementation used to reach that result must be generic enough that the same primitives can support other bug reports without adding a new per-bug feature

### Phase 4: Replace Narrow Fix Branches With A Bounded Edit Workflow

Implement:

- evidence-ranked candidate file set
- edit proposal payload
- bounded patch application for `.gd` and `.tscn`

Acceptance:

- the system can repair at least one seeded hit-feedback bug without adding a dedicated one-off handler for that exact bug kind
- the same edit workflow must be usable by the model for other bug reports as long as the evidence points to defensible candidate files

Current status:

- the bounded edit mechanism is implemented
- the real seeded hit-feedback validation round is still pending

### Phase 5: Expose One Top-Level Repair Workflow

Implement:

- top-level `repair_reported_bug` style workflow
- final verification summary for the full run

Acceptance:

- one explicit user request can drive the full sequence from intake to rerun and regression

Current status:

- `repair_reported_bug` is implemented
- it runs the sequence as far as the currently supplied model inputs allow
- if no model evidence plan or no bounded fix proposal is supplied, it returns a concrete `blocking_point` and `next_action`

### Phase 6: Validate On Real Bug Rounds And Document User Contract

Implement:

- controlled test-project rounds for behavior bugs
- restore verification after each round
- updated user-facing docs for the new request type

Acceptance:

- the workflow succeeds on at least one real seeded behavior bug
- the test project restores cleanly after each round
- the user-facing command guide documents the new request shape

## Final Acceptance Standard

This target should be considered implemented only when all of the following are true:

1. a new-project user can make one explicit natural-language repair request
2. GPF can reproduce the bug in real `play_mode`
3. GPF can persist evidence that explains why the bug is real
4. GPF can apply a bounded code or scene fix based on that evidence
5. GPF can rerun the same repro and then run regression
6. GPF can report `fixed and verified` only when the rerun and regression both pass
7. when the run cannot finish, GPF reports one concrete `blocking_point`, one explicit `next_action`, and the artifact files that support that result

## What Should Not Be Treated As Success

The repository should not claim this target is complete if any of these are still true:

- the workflow still requires a human to manually translate the user sentence into CLI fields every time
- the workflow can only fix the bug by adding one dedicated handler for that single bug kind
- the workflow cannot produce runtime evidence for a time-based visual change
- the workflow applies edits without rerun and regression
- the workflow reports success based only on model reasoning

## Repository Decision Going Forward

When choosing the next implementation task for bug work, prefer tasks that move the repository toward this recorded user scenario:

- new-project installation
- explicit natural-language bug repair request
- real `play_mode` repro
- evidence-backed edit
- rerun plus regression

Do not treat additional fixed bug categories by themselves as the main measure of progress.
They are useful only when they help validate the broader workflow above.

The main question for every next implementation step should be:

- does this give the model a better generic tool for inspection, execution, editing, or verification

The wrong question is:

- does this add support for one more named bug category
