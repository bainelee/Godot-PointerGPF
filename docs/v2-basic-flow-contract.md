# V2 Basic Flow Contract

## Purpose

This document defines the product contract for `basicflow` in V2.

It is based on the intended real user scenarios:

- first-time value demonstration is the primary goal
- ongoing baseline confidence check is the secondary goal

Reference:

- [v2-basic-flow-user-intent.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-user-intent.md)

## Asset Model

`basicflow` should be treated as one explicit project asset.

Decision:

- keep a single current file
- overwrite that file when the user explicitly regenerates it
- do not build local history into GPF by default

Reasoning:

- assume users rely on Git for version history
- keep the MCP side simple

## Regeneration Rules

`basicflow` must not silently drift.

It changes only when:

1. the user explicitly requests regeneration
2. the user requests to run the basic flow, and GPF detects that project changes are large enough that the old flow may no longer be meaningful

Even in case 2, GPF should not silently update it.

Default behavior:

- warn
- explain why the old `basicflow` may be stale
- ask what to do next

## Large-Change Detection Policy

The change detector should be intentionally conservative.

Priority order:

1. files directly related to the existing `basicflow`
2. broad project code/file change volume
3. startup scene / critical runtime path changes

Design preference:

- err on the side of warning too often rather than missing a meaningful change
- prefer simpler and more robust checks over highly specific but fragile logic

## First-Time Generation Behavior

When GPF generates `basicflow` for the first time, it should ask the user key questions first.

Decision:

- asking the user is preferred over full silent generation

This means the expected flow is:

1. inspect the project
2. form candidate understanding
3. ask key questions
4. generate the simplest useful `basicflow`

## Required Step Types

Default required parts of a `basicflow`:

- launch the project
- enter an interactive state
- perform at least one visible click/input
- perform at least one baseline assertion
- close the running game at the end

Optional parts:

- scene transition or state change
- screenshot evidence

Not in scope for now:

- video recording evidence

## Assertion Policy

Assertion selection should be project-aware, but one baseline rule must always hold.

Decision:

- the minimum guaranteed assertion is: the project launched, stayed running long enough to reach the target state, and did not immediately crash

Priority:

1. always satisfy baseline "project runs and reaches target state without immediate fatal failure"
2. add UI/node visibility assertions when the project state supports them
3. add feedback assertions when the project has a meaningful interaction surface

This means even sparse projects or near-empty scenes still have a valid baseline assertion path.

## Stale Basic Flow Warning Policy

Warnings for possible stale `basicflow` should be aggressive rather than permissive.

Decision:

- warn early
- favor false positives over false negatives

Reasoning:

- warning too often is safer than quietly running a no-longer-meaningful baseline flow

## User Choices When Old Basic Flow May Be Stale

When the user requests `run basic flow` and GPF detects significant change, GPF should ask and offer these paths:

1. analyze what the old `basicflow` did and where it no longer matches the current project
2. regenerate `basicflow`
3. let the user describe project changes or give other requirements
4. run the old `basicflow` anyway

If the user chooses to run the old `basicflow` and it fails:

- first analyze the failure and the gap between old flow assumptions and current project state
- then suggest regeneration
- do not auto-update `basicflow`

## Meaning Of "Project Foundation Is Still Intact"

For experienced users, passing `basicflow` is a baseline confidence check.

It means at least:

- the project launches
- the basic startup/runtime path still works
- the basic functionality is not obviously broken
- there is no immediate crash
- there is no obvious severe issue that must be fixed before continuing development

It does not mean:

- full regression coverage
- full gameplay verification
- deep correctness of all newly added systems
