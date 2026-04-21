# 2026-04-21 GPF Bug Seeding And Restoration Rules

## Purpose

This document defines how the repository should use the external test project when developing GPF's bug analysis, reproduction, repair, and verification features.

The goal is to keep all verification work tied to bugs that are **actually present** in the test project.

## Main Rule

When developing GPF's bug repair workflow:

- it is allowed to intentionally add bugs to the test project
- it is not allowed to pretend a bug exists when it does not
- it is not allowed to use made-up success or failure targets that have no real meaning in the test project

## Allowed Practice

The agent may intentionally edit the test project to create one or more realistic bugs.

Examples:

- remove or break a signal connection
- break a scene transition
- introduce a wrong property value
- change scene or UI visibility logic
- add multiple small faults across separate files

The injected bug may be:

- obvious
- subtle
- spread across more than one file
- similar to the kind of mistake a real developer might make

## Forbidden Practice

The following are not acceptable verification methods:

- using a wrong assertion to force a healthy project to look broken
- treating a missing old node as proof of failure when scene transition success already removed that node from the tree
- using a made-up target condition that is not a real expected state of the project
- claiming the repair workflow works when the test project never actually contained the bug being discussed

## Required Recording Before Bug Injection

Before the first test-project edit for a given bug-development round, record the original state.

Record at least:

- test project path
- round timestamp
- bug description to be tested
- files that will be modified
- original contents of every file that will be modified
- short explanation of each injected bug

If the work affects any editor-saved state, also record the original versions of the affected:

- `.tscn`
- `.tres`
- `.res`
- `project.godot`

## Required Storage Location

These records must be written to a durable file location, not only stated in chat.

Recommended location inside the test project:

- `pointer_gpf/tmp/bug_dev_rounds/<round_id>/`

Recommended files for each round:

- `baseline_manifest.json`
- `baseline_files/<...>`
- `bug_injection_plan.json`
- `restore_plan.json`

## Required Restore Rule

After the feature-development round ends, the agent must restore the test project to the recorded original state.

Restore work must:

- target every modified file from the round
- use the recorded original contents
- remove temporary verification-only changes

After restore, the agent must run the necessary validation again and confirm that the test project is back to the expected normal state.

## Required Workflow

The workflow for future bug-repair feature development must be:

1. choose the bug scenario to validate
2. record the original state of the test project
3. inject a real bug into the test project
4. use that real bug to develop and validate GPF
5. restore the test project
6. verify the restored state

## Reporting Rule

When reporting progress, always state:

- whether the current bug came from the original test project or was intentionally injected
- which files were changed to create it
- whether the test project has already been restored

## What This Rule Fixes

This rule exists because the repository must not continue validating the repair workflow against bug targets that are not truly present in the test project.

GPF should be judged by whether it can:

- analyze a real bug
- reproduce a real bug
- plan a fix for a real bug
- verify the repair of a real bug

That is the only valid basis for this stage of development.
