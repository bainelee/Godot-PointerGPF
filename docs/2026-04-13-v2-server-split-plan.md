# 2026-04-13 V2 Server Split Plan

This document records the intended split plan for:

- [server.py](/D:/AI/pointer_gpf/v2/mcp_core/server.py)

It exists so the work can be resumed later without rediscovering:

- whether the file is already too large
- whether MCP requires a single-file server entry
- when the split should happen
- what the split boundaries should be

## Current Judgment

Current judgment:

- `server.py` is already too large for long-term maintenance
- MCP does **not** require everything to stay in one file
- the file should be split
- the split should happen **after the current user-request layer slice is stabilized**
- the split should happen **before** a third high-level request domain is added

This timing is intentional.

If the split is delayed too long:

- more user-request logic will accumulate in `server.py`
- more cross-cutting helper functions will be added
- future extraction cost will increase

If the split is done too early:

- the current request-layer boundaries may still move unnecessarily

So the preferred window is:

- finish the current bounded user-request slice
- then split `server.py`
- then continue expanding other top-level domains

## Why The Split Is Needed

`server.py` currently mixes several responsibilities:

- CLI argument parsing and top-level tool dispatch
- flow execution orchestration
- teardown verification
- user-request catalogs, routing, planning, and handling
- process / runtime helper functions

This makes it harder to:

- reason about ownership
- review changes safely
- keep tests aligned with one coherent module boundary

## What MCP Does And Does Not Require

MCP does not require:

- one Python file for all tool logic

MCP does require:

- a stable tool entrypoint and dispatch path

So the correct split model is:

- keep a thin `server.py` entrypoint
- move internal logic into adjacent modules
- preserve the same external tool names and CLI behavior

## Proposed Split Shape

### 1. Keep In `server.py`

Only keep:

- argument parsing
- top-level dispatch
- tool-to-function mapping
- shared `_ok` / `_err` wrappers if still useful

`server.py` should become the thinnest possible entry shell.

### 2. Move User-Request Layer

Create a module such as:

- `request_layer.py`

Move there:

- request specs / catalogs
- `get_basic_flow_user_intents` support helpers
- `resolve_basic_flow_user_request`
- `plan_basic_flow_user_request`
- `plan_user_request`
- `handle_user_request`
- command-guide helpers

Reason:

- these functions form one coherent product-facing layer

### 3. Move Flow Orchestration

Create a module such as:

- `runtime_orchestration.py`

Move there:

- `run_basic_flow` tool orchestration wrapper
- play-mode / isolated-runtime launch handling
- flow lock integration
- plugin sync + preflight + launch chain around flow execution

Reason:

- this is one runtime execution concern, not a user-request concern

### 4. Move Teardown Verification

Create a module such as:

- `teardown_verification.py`

Move there:

- teardown stability checks
- runtime stop verification helpers
- process-count stop heuristics

Reason:

- teardown logic is already a separate concern and should stop living beside planner logic

### 5. Optionally Move Process Probes

If the split still leaves too much runtime plumbing mixed together, extract:

- `process_probe.py`

for:

- project process listing
- editor/runtime PID checks
- related helper probes

This is optional.
Do it only if the first split still leaves the orchestration module too noisy.

## Required Constraints For The Split

When this split happens, keep these constraints:

1. Do not change tool names as part of the refactor.
2. Do not change externally observed payload shapes unless that change is separately intended and documented.
3. Keep behavior-preserving tests in place before moving code.
4. Prefer moving existing tested functions first, then renaming only if needed.
5. Do not mix this refactor with unrelated feature growth.

## Verification Requirements

When the split is executed, verification should include at minimum:

- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_server.py`
- targeted tests for any newly created modules
- at least one real command for:
  - `get_user_request_command_guide`
  - `handle_user_request --user-request "跑项目预检"`
  - `resolve_basic_flow_user_request --user-request "run basicflow"`

If the split touches flow orchestration in the same slice, also run:

- `python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame`

## Trigger Condition

This plan should be picked up when either of these becomes true:

- the current bounded request-layer work is considered complete enough for a refactor pause
- a new high-level request domain is about to be added

At that point, prefer doing the split first.

## Non-Goal

This plan is not for:

- redesigning the external MCP contract
- making natural-language support broader
- changing the product boundary of V2

It is only for making the current validated structure maintainable.
