# 2026-04-21 GPF Next Development Plan

## Purpose

This plan turns the current status gap into a small number of concrete repository tasks.

The plan is intentionally narrow:

- keep the current bug-report and repro classification work
- add the missing verification steps after code changes
- avoid growing new planner or language features during this work

## Step 1: Rerun The Same Bug-Focused Flow

### Required Result

Add a tool that:

1. loads the latest confirmed bug repro artifact
2. uses the same planned bug-focused flow
3. reruns that flow after code changes
4. writes a separate verification result artifact

### Files To Change

- `v2/mcp_core/bug_repro_execution.py`
- `v2/mcp_core/tool_dispatch.py`
- `v2/mcp_core/server.py`
- matching unit tests

### Acceptance

- the rerun tool does not rebuild a new bug plan by default
- the rerun tool does not overwrite the original repro artifact
- the rerun result clearly reports whether the bug is still reproduced

## Step 2: Run Regression After A Passing Rerun

### Required Result

Add a tool that:

1. runs the existing regression command for the current project
2. records the command result
3. returns a small machine-readable payload

### Files To Change

- a new bug-fix verification module or a focused regression module
- `v2/mcp_core/tool_dispatch.py`
- `v2/mcp_core/server.py`
- matching unit tests

### Acceptance

- regression is not run if the bug-focused rerun still reproduces the bug
- regression output includes command, exit code, and summary

## Step 3: Add One Repair Verification Tool

### Required Result

Add a tool that performs this sequence:

1. apply a supported bug fix
2. rerun the same bug-focused flow
3. run regression if the rerun passes
4. return one final verification payload

### Files To Change

- a new verification coordinator module
- `v2/mcp_core/tool_dispatch.py`
- `v2/mcp_core/server.py`
- matching unit tests

### Acceptance

- the final payload clearly separates:
  - fix application result
  - bug-focused rerun result
  - regression result
- the final payload reports success only when all required checks pass

## Step 4: Update Repository Documentation

### Required Result

After the new tools exist, update:

- `docs/v2-status.md`
- `docs/v2-handoff.md`

### Acceptance

- the documents describe the current bug-repair workflow accurately
- obsolete planner-growth language is removed where needed

## Execution Rule

During this plan:

- do not add new planner heuristics
- do not add new natural-language routing
- do not expand `basicflow` product work unless a test proves it is required
- prefer a small number of explicit result files and explicit tool outputs
