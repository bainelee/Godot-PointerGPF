# 2026-04-14 GPF Bug Intake And Assertion Contract

## Purpose

This document defines the first concrete contract slice for the new GPF core loop:

1. accept a bounded bug report
2. turn it into structured analysis input
3. define explicit correct-state assertions before fixing anything

This is the first implementation target after the completed server split.

Reference:

- [2026-04-14-gpf-core-direction.md](/D:/AI/pointer_gpf/docs/2026-04-14-gpf-core-direction.md)

## Why This Slice Comes First

Without this slice, the rest of the loop stays vague:

- bug reproduction is under-specified
- flow design has no machine-checkable target
- code fixing risks chasing the wrong symptom

The core rule is:

- do not jump straight from free-form bug text to code edits

Instead, the system should first produce:

- a structured bug-intake payload
- a small evidence-backed cause-analysis summary
- a correct-state assertion set

## Scope

This slice should cover:

- bug-focused natural-language intake
- bounded gray-box analysis against the Godot project
- explicit assertion generation

This slice should not yet cover:

- full autonomous fixing
- open-ended conversation routing
- broad bug taxonomy
- sophisticated multi-branch planning

## Core Loop Position

This document covers only the first three stages of the full loop:

1. user bug report
2. likely-cause analysis
3. correct-state assertion definition

The later stages remain separate:

4. repro flow selection or patching
5. reproduction run
6. fix planning and code edit
7. re-verification

## Contract 1: Bug Intake

### Goal

Convert a bounded natural-language bug description into a structured bug case that later tools can consume.

### Input Shape

The user can describe a bug in ordinary language, but the system should normalize it into these fields:

- `summary`
- `steps_to_trigger`
- `observed_behavior`
- `expected_behavior`
- `location_hint`
- `frequency_hint`
- `severity_hint`
- `extra_context`

### Required Fields

Minimum required fields for a valid bug intake case:

- `observed_behavior`
- `expected_behavior`

At least one of these should also be present:

- `steps_to_trigger`
- `location_hint`
- `summary`

### Normalized Payload Shape

Suggested normalized payload:

```json
{
  "schema": "pointer_gpf.v2.bug_intake.v1",
  "summary": "Clicking Start Game does not enter the playable level",
  "steps_to_trigger": [
    "launch the project",
    "wait for the main menu",
    "click Start Game"
  ],
  "observed_behavior": "The game stays on the menu and does not enter the next scene",
  "expected_behavior": "The game should enter the playable level scene",
  "location_hint": {
    "scene": "Boot/MainMenu",
    "node": "StartButton",
    "script": ""
  },
  "frequency_hint": "always",
  "severity_hint": "core_progression_blocker",
  "extra_context": {
    "user_words": "点开始游戏没有反应"
  }
}
```

### Product Rules

- the intake step should stay bug-focused rather than becoming a general NL interface
- the tool should preserve the user's words, but return a normalized structure
- if the description is too vague, the system should ask for missing bug-critical fields rather than pretending it has enough
- the intake step should not claim a root cause yet

## Contract 2: Cause Analysis

### Goal

Turn the intake payload into a narrow, gray-box analysis summary based on project facts.

### Inputs

Cause analysis should use:

- the normalized bug intake payload
- the current project structure
- related scenes and scripts
- existing project-local flow assets if they help locate the affected path

### Expected Output

The result should be a compact analysis payload, not a long explanation.

Suggested output shape:

```json
{
  "schema": "pointer_gpf.v2.bug_analysis.v1",
  "bug_summary": "Clicking Start Game does not enter the playable level",
  "suspected_causes": [
    {
      "kind": "scene_transition_not_triggered",
      "confidence": "medium",
      "reason": "Start button exists, but the target scene transition path is a likely failure point"
    },
    {
      "kind": "button_signal_or_callback_broken",
      "confidence": "medium",
      "reason": "User action is a UI click and the symptom is no response"
    }
  ],
  "affected_artifacts": {
    "scenes": ["res://scenes/boot.tscn", "res://scenes/main_menu.tscn"],
    "nodes": ["StartButton"],
    "scripts": ["res://scripts/main_menu.gd"]
  },
  "evidence": [
    "project startup path points to the menu scene",
    "bug location hint references Start Game interaction"
  ],
  "recommended_assertion_focus": [
    "scene transition should occur",
    "menu should not remain the active scene after click"
  ]
}
```

### Product Rules

- analysis must stay evidence-backed and project-scoped
- analysis should produce a small set of plausible causes, not a broad speculative list
- analysis should help assertion generation, not replace it
- analysis should be allowed to return uncertainty

## Contract 3: Correct-State Assertion

### Goal

Define what "the bug is absent" means in machine-checkable form.

### Main Rule

Do not define the bug only as a failure symptom.

Define the desired non-bug state as explicit assertions.

Examples:

- a scene transition should happen
- a node should become visible
- a node should remain enabled
- a runtime value should stay within bounds
- a known engine/runtime error should not appear

### Assertion Payload Shape

Suggested output shape:

```json
{
  "schema": "pointer_gpf.v2.assertion_set.v1",
  "bug_summary": "Clicking Start Game does not enter the playable level",
  "assertions": [
    {
      "id": "scene_transition_to_game_level",
      "kind": "scene_active",
      "target": {
        "scene": "res://scenes/game_level.tscn"
      },
      "operator": "equals",
      "expected": true,
      "reason": "The correct result of clicking Start Game is entering the playable level"
    },
    {
      "id": "main_menu_not_still_active_after_start",
      "kind": "scene_active",
      "target": {
        "scene": "res://scenes/main_menu.tscn"
      },
      "operator": "equals",
      "expected": false,
      "reason": "The menu should no longer remain the active scene after successful start"
    }
  ]
}
```

### Assertion Design Rules

- assertions should describe the correct target state, not only the broken symptom
- assertions should be small, explicit, and independently checkable
- assertions should prefer direct observable state over vague textual conclusions
- assertions may include both positive and negative expectations
- assertions should be reusable during both reproduction and post-fix verification

## Implementation Sequence

Recommended build order:

1. add a bounded `collect_bug_report` entrypoint
2. add a `analyze_bug_report` entrypoint that reads project facts
3. add a `define_bug_assertions` entrypoint
4. only then wire those outputs into repro-flow planning

## Recommended CLI / Tool Surface

The first concrete tool slice should likely expose:

- `collect_bug_report`
- `analyze_bug_report`
- `define_bug_assertions`

Suggested progression:

- `collect_bug_report` returns `pointer_gpf.v2.bug_intake.v1`
- `analyze_bug_report` returns `pointer_gpf.v2.bug_analysis.v1`
- `define_bug_assertions` returns `pointer_gpf.v2.assertion_set.v1`

These should remain bounded tools rather than a broad free-form bug assistant.

## Definition Of Done For This Slice

This first slice is complete when:

1. GPF can accept a bounded bug report and normalize it
2. GPF can analyze likely affected project artifacts for that bug
3. GPF can emit explicit correct-state assertions for the bug
4. those contracts are documented and covered by unit tests
5. later repro-flow work can consume these outputs directly
