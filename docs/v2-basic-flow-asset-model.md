# V2 Basic Flow Asset Model

## Purpose

This document defines the concrete asset shape for `basicflow` in V2.

It turns the product contract into an implementation-facing storage model.

Reference:

- [v2-basic-flow-contract.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-contract.md)

## Files

V2 should treat the project baseline flow as two sibling files:

1. `basicflow.json`
2. `basicflow.meta.json`

Reasoning:

- keep one explicit current flow file
- keep metadata separate from executable flow steps
- avoid mixing human-facing lifecycle state into the runtime step list

## `basicflow.json`

`basicflow.json` stores the executable baseline flow only.

It should contain:

- the flow step list
- any runtime arguments needed to execute that flow
- no historical versions
- no stale-check bookkeeping

This file is the single current baseline flow asset.

When the user explicitly regenerates `basicflow`, this file is overwritten.

## `basicflow.meta.json`

`basicflow.meta.json` stores the current flow's lifecycle metadata.

Initial required fields:

- `generated_at`
- `generation_summary`
- `related_files`
- `project_file_summary`
- `last_successful_run_at`

## Field Meaning

### `generated_at`

UTC timestamp for when the current `basicflow.json` was generated.

Use:

- explain how old the current flow is
- support stale-flow warning text

### `generation_summary`

Short natural-language explanation of what the current `basicflow` is meant to prove.

Use:

- give the user a quick reminder before running or regenerating
- explain why this flow exists without forcing them to inspect raw JSON

### `related_files`

List of files directly used to derive the current `basicflow`.

This list should be intentionally small and explainable.

Examples:

- startup scene file
- scene script used by the tested interaction
- UI scene file for a tested button or HUD

Use:

- primary signal for aggressive stale-flow detection
- basis for "these specific files changed" warnings

### `project_file_summary`

Small project-wide summary captured at generation time.

It should stay simple and cheap to compute.

Initial shape can be:

- total file count under the project root
- total script count
- total scene count

Use:

- broad secondary signal for "project changed a lot"
- avoid expensive or fragile deep project comparisons in phase 2

### `last_successful_run_at`

UTC timestamp for the most recent successful `run_basic_flow` execution using the current asset pair.

Use:

- explain whether the current flow has been proven recently
- help the user understand if a flow is old and unverified

This field should update only after a successful baseline run.

## Versioning Rule

V2 should not build local history into the MCP for `basicflow`.

Decision:

- only keep the current `basicflow.json`
- only keep the current `basicflow.meta.json`
- rely on Git for history

This keeps the asset model small and predictable.

## Storage Rule

The asset pair should live in a stable project-local location.

Implementation rule:

- keep both files near the project-local Pointer GPF runtime area or another explicit project-local GPF directory
- do not hide them in transient temp-only state

The user should be able to understand:

- there is a current baseline flow
- there is metadata describing where it came from

## Regeneration Rule

Regeneration replaces both files together.

That means:

- write the new `basicflow.json`
- write the matching new `basicflow.meta.json`
- do not leave mixed old/new pairs

## Run-Time Rule

Running `run_basic_flow` must not silently rewrite `basicflow.json`.

Allowed updates during normal execution:

- update `last_successful_run_at` after a successful run

Not allowed during normal execution:

- silently replace the flow steps
- silently replace `related_files`
- silently change the generation summary

## Immediate Implementation Consequence

Before adding automatic regeneration logic, V2 should first add:

1. a loader for `basicflow.json` + `basicflow.meta.json`
2. a validator for required metadata fields
3. a clear missing-asset path for first-time generation
