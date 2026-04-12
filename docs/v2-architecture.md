# V2 Architecture

## Purpose

V2 exists to replace the old overly heavy MCP core with a smaller, auditable system.

For the user-facing meaning of "run the basic test flow", see:

- [v2-basic-flow-user-intent.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-user-intent.md)
- [v2-basic-flow-contract.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-contract.md)
- [v2-basic-flow-asset-model.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-asset-model.md)
- [v2-basic-flow-staleness-and-generation.md](/D:/AI/pointer_gpf/docs/v2-basic-flow-staleness-and-generation.md)

The main rule is:

- core testing first
- advanced automation later

## Scope of V2 Phase 1

V2 phase 1 includes:

- configure Godot executable
- sync plugin into target project
- run preflight
- generate project-local `basicflow` assets
- run file-bridge flows through `run_basic_flow`
- support `launchGame`, `click`, `wait`, `check`, `closeProject`
- verify teardown after `closeProject`
- reject overlapping flows for one project
- reject manual multi-editor runs for one project
- support an experimental `isolated_runtime` execution mode on Windows
- warn when project-local `basicflow` assets look stale
- allow explicit stale-flow override through `--allow-stale-basicflow`
- expose a stale-analysis entrypoint for comparing old `basicflow` assumptions against the current project snapshot
- accept direct structured answers for the 3 `basicflow` generation questions
- expose a question-contract entrypoint so the UI/conversation layer can fetch those 3 questions explicitly
- expose a session-based question flow so the UI/conversation layer can collect answers step by step without its own state store

## Module Boundaries

### MCP core

Located in:

- [v2/mcp_core](/D:/AI/pointer_gpf/v2/mcp_core)

Responsibilities:

- CLI tool entrypoints
- preflight checks
- plugin sync
- Windows isolated-runtime launch and stop verification
- basicflow asset generation/loading/stale detection
- launching editor if needed
- entering play mode
- file-bridge flow execution
- teardown verification
- same-project flow guard
- same-project multi-editor detection

### Godot plugin

Located in:

- [v2/godot_plugin/addons/pointer_gpf](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf)

Responsibilities:

- editor plugin updates `runtime_gate.json`
- runtime bridge consumes `command.json`
- runtime bridge writes `response.json`
- diagnostics writer records engine and bridge errors

### External test project

Primary validation target:

- `D:\AI\pointer_gpf_testgame`

Responsibilities:

- act as real integration target
- catch engine-side resource and scene issues
- validate V2 against actual Godot project behavior

## What V2 Explicitly Does Not Include Yet

These old-system areas are intentionally excluded:

- auto-fix
- repair loop
- NL intent router
- orchestration
- Figma baseline/UI compare pipeline

## Why This Split Exists

The old system proved that these concerns should not share one huge server core.

Observed old-system failure mode:

- project resource errors and runtime scene errors were often misread as MCP failures
- stale gate files and broad server responsibilities made debugging much harder

V2 is designed so that:

- preflight catches project-level issues earlier
- runtime flow runner stays small
- plugin responsibilities stay narrow
- execution mode can evolve beyond editor `play_mode` without rewriting the bridge contract

## Phase 2 Direction

Phase 1 already covers the smallest interactive loop. It now has two runtime paths:

- validated default `play_mode`
- experimental Windows `isolated_runtime` that launches the game on a dedicated desktop and verifies shutdown through `runtime_session.json` plus runtime PID

The next architecture step should focus on turning that loop into a stable project asset:

1. keep `run_basic_flow` as the code-facing command, while treating `basicflow` as a persistent project-local asset pair
2. detect when the current `basicflow` may be stale using simple conservative rules
3. keep the explicit stale-flow override and stale-analysis entrypoint, then add the remaining regenerate UX around them
4. connect the question-contract or session entrypoints to the final question-first UX
5. only then expand runtime assertions or snapshot-style checks
