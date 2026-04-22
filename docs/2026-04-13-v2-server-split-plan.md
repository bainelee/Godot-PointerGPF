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

- the planned split has now been executed
- MCP did **not** require everything to stay in one file
- `server.py` is now reduced to a thinner entry shell plus compatibility wrappers
- the main follow-up is no longer "whether to split", but "how much wrapper compatibility should remain in `server.py`"

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

## Executed Split Shape

### 1. Keep In `server.py`

Current contents:

- argument parsing
- top-level exception exit behavior
- shared `_ok` / `_err` wrappers
- dependency wiring into the dispatch layer
- compatibility wrappers used by existing CLI-oriented tests

Current result:

- `server.py` is no longer the primary home for request logic or runtime orchestration
- the file is substantially smaller than before the split
- the main remaining cleanup question is whether some compatibility wrappers should eventually be deleted after more test migration

### 2. Move User-Request Layer

Implemented as:

- `request_layer.py`

Current contents:

- request specs / catalogs
- `get_basic_flow_user_intents` support helpers
- `resolve_basic_flow_user_request`
- `plan_basic_flow_user_request`
- `plan_user_request`
- `handle_user_request`
- command-guide helpers

Status:

- completed

### 3. Move Flow Orchestration

Implemented as:

- `runtime_orchestration.py`

Current contents:

- `run_basic_flow` tool orchestration wrapper
- play-mode / isolated-runtime launch handling
- flow lock integration
- plugin sync + preflight + launch chain around flow execution

Status:

- completed
- the module now delegates narrower concerns outward instead of keeping all runtime helpers inside one file

### 4. Move Teardown Verification

Implemented as:

- `teardown_verification.py`

Current contents:

- teardown stability checks
- runtime stop verification helpers
- process-count stop heuristics

Status:

- completed

### 5. Move Process Probes

Implemented as:

- `process_probe.py`

Current contents:

- project process listing
- editor/runtime PID checks
- related helper probes

Status:

- completed

### 6. Add Thin Dispatch Layer

Implemented as:

- `tool_dispatch.py`

Current contents:

- top-level tool branching formerly embedded in `server.py`
- tool-specific argument validation at the dispatch layer
- packaging of return payloads from lower modules

Status:

- completed

## Required Constraints For The Split

The executed split kept these constraints:

1. Do not change tool names as part of the refactor.
2. Do not change externally observed payload shapes unless that change is separately intended and documented.
3. Keep behavior-preserving tests in place before moving code.
4. Prefer moving existing tested functions first, then renaming only if needed.
5. Do not mix this refactor with unrelated feature growth.

## Observed Verification

The split work was verified with these command patterns:

- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_server.py`
- targeted tests for the new modules:
  - `test_request_layer.py`
  - `test_runtime_orchestration.py`
  - `test_process_probe.py`
  - `test_teardown_verification.py`
  - `test_tool_dispatch.py`
- at least one real command for:
  - `get_user_request_command_guide`
  - `handle_user_request --user-request "跑项目预检"`
  - `resolve_basic_flow_user_request --user-request "run basicflow"`
- `python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame`

Latest observed state after test migration:

- `test_server.py` now focuses more on CLI smoke and compatibility behavior
- module-level behavior is increasingly covered in the module-specific test files
- the fixed regression bundle currently reports `v2_unit_tests` with `Ran 81 tests`, `OK`

## Current Repository Shape After Split

Current module split under `v2/mcp_core/` is:

- `server.py`
- `tool_dispatch.py`
- `request_layer.py`
- `runtime_orchestration.py`
- `process_probe.py`
- `teardown_verification.py`

This is now the maintained baseline for further V2 work.

## Current Follow-Up

The next preferred work is no longer more server splitting by default.

Preferred follow-up:

1. keep shrinking `test_server.py` only where the moved module tests clearly replace wrapper-only assertions
2. update handoff / status docs when the split shape changes
3. return focus to `basicflow` productization and runtime-isolation work unless a new top-level request domain forces another dispatch refactor

## Non-Goal

This plan is not for:

- redesigning the external MCP contract
- making natural-language support broader
- changing the product boundary of V2

It is only for making the current validated structure maintainable.
