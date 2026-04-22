# Pointer GPF V2

<p align="center">
  <img src="./pointer_gpf_logo.png" alt="PointerGPF logo" width="780" />
</p>

[简体中文（Default）](./README.md) | **English**

Pointer GPF is an MCP toolchain for **Godot gray-box testing**.

Its current goal is intentionally narrow:

- connect a Godot project to an executable test pipeline
- generate and maintain a project-local `basicflow`
- drive bug reproduction, evidence collection, and repair planning through explicit tools and a bounded natural-language layer

It is **not** trying to become an open-ended agent that understands everything.

## What It Can Do Today

The current V2 on `main` can:

- configure the Godot executable path
- sync the V2 plugin into a target project
- run project `preflight`
- generate `basicflow.json` and `basicflow.meta.json`
- analyze why the current `basicflow` is stale
- execute `run_basic_flow`
- support `click`, `wait`, `check`, and `closeProject`
- verify teardown after the flow ends
- reject overlapping flow runs and multiple-editor conflicts
- provide a **bounded** natural-language entry layer
- return bug observation summaries, investigation plans, and executable check sets
- persist `executable_checks`, `check_results`, and `check_summary` into the repro artifact
- return `evidence_summary`, `acceptance_checks`, candidate files, and fix goals from `plan_bug_fix`

The supported high-frequency user request areas are currently:

- run the basic test flow
- regenerate the basic flow
- analyze why the basic flow is stale
- run project preflight
- configure the Godot executable path

The current mainline has also shifted from “enumerate more fixed bug kinds” to “let the model decide how to inspect, check, and validate within explicit execution boundaries.”

## What It Is Not

V2 does **not** currently promise:

- open-domain natural-language understanding
- one-shot orchestration for vague, broad requests
- automatic repair of arbitrary project problems
- endless phrase expansion just to feel “smarter”

For the current boundary, read:

- [How to command GPF](./docs/v2-how-to-command-gpf.md)
- [Natural-language boundary principles](./docs/v2-natural-language-boundary-principles.md)

For the current product direction, read:

- [2026-04-22 GPF Model-Driven Bug Loop Plan](./docs/2026-04-22-gpf-model-driven-bug-loop-plan.md)

## Recommended Starting Path

The safest way to start is:

1. read the status docs
2. configure the Godot path
3. run project preflight
4. inspect the supported command boundary
5. then decide whether to generate a `basicflow` or run an existing one

### 1. Reading path for users

If you are a user, maintainer, or tester, start with:

- [V2 status](./docs/v2-status.md)
- [V2 architecture](./docs/v2-architecture.md)
- [V2 handoff](./docs/v2-handoff.md)

These answer:

- what the project can already do
- how the current system is structured
- where a new collaborator should resume work

### 2. Reading path for coding assistants / AI agents

If you want a coding assistant to continue implementation, debugging, or validation, it should read:

- [docs/v2-status.md](./docs/v2-status.md)
- [docs/v2-how-to-command-gpf.md](./docs/v2-how-to-command-gpf.md)
- [docs/v2-natural-language-boundary-principles.md](./docs/v2-natural-language-boundary-principles.md)
- [docs/v2-handoff.md](./docs/v2-handoff.md)

This set is better for:

- current workstream state
- user-command boundary
- what NL support should not become
- where the next development turn should resume

### 3. Run the fixed regression bundle

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame
```

### 4. Inspect the supported command guide

```powershell
python -m v2.mcp_core.server --tool get_user_request_command_guide --project-root D:\AI\pointer_gpf_testgame
```

### 5. Typical commands

Project preflight:

```powershell
python -m v2.mcp_core.server --tool preflight_project --project-root D:\AI\pointer_gpf_testgame
```

Project preflight through the bounded NL layer:

```powershell
python -m v2.mcp_core.server --tool handle_user_request --project-root D:\AI\pointer_gpf_testgame --user-request "run preflight"
```

Get basicflow generation questions:

```powershell
python -m v2.mcp_core.server --tool get_basic_flow_generation_questions --project-root D:\AI\pointer_gpf_testgame
```

Run the basic flow:

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame
```

Generate bug observation, checks, and an investigation plan:

```powershell
python -m v2.mcp_core.server --tool observe_bug_context --project-root D:\AI\pointer_gpf_testgame --bug-report "clicking Start stays on the menu" --expected-behavior "the game should enter the level" --location-scene res://scenes/main_scene_example.tscn --location-node StartButton --location-script res://scripts/main_menu_flow.gd
python -m v2.mcp_core.server --tool define_bug_checks --project-root D:\AI\pointer_gpf_testgame --bug-report "clicking Start stays on the menu" --expected-behavior "the game should enter the level" --location-scene res://scenes/main_scene_example.tscn --location-node StartButton --location-script res://scripts/main_menu_flow.gd
python -m v2.mcp_core.server --tool plan_bug_investigation --project-root D:\AI\pointer_gpf_testgame --bug-report "clicking Start stays on the menu" --expected-behavior "the game should enter the level" --location-scene res://scenes/main_scene_example.tscn --location-node StartButton --location-script res://scripts/main_menu_flow.gd
```

Run a bug repro in `play_mode` and read the evidence-backed fix plan:

```powershell
python -m v2.mcp_core.server --tool run_bug_repro_flow --project-root D:\AI\pointer_gpf_testgame --execution-mode play_mode --bug-report "clicking Start stays on the menu" --expected-behavior "the game should enter the level" --location-scene res://scenes/main_scene_example.tscn --location-node StartButton --location-script res://scripts/main_menu_flow.gd
python -m v2.mcp_core.server --tool plan_bug_fix --project-root D:\AI\pointer_gpf_testgame --bug-report "clicking Start stays on the menu" --expected-behavior "the game should enter the level" --location-scene res://scenes/main_scene_example.tscn --location-node StartButton --location-script res://scripts/main_menu_flow.gd
```

## Current Practical Effect

Today, after a user describes a bug, GPF can already:

1. summarize project structure, runtime diagnostics, recent repro evidence, and recent verification evidence
2. generate explicit checks instead of only giving a vague suggestion
3. run the repro in real `play_mode` and persist which checks failed and which checks did not run
4. build a repair plan from that evidence

The current system is already useful for cases such as:

- a UI click does not trigger a scene transition
- a node is missing or renamed
- a HUD does not appear after entering gameplay
- a repro already fails reliably, but the team still needs clearer failure evidence and better candidate files

## Current Release Shape

V2 now has a smoke-verified minimal release path:

- build a source-bundle zip
- unpack it and run the V2 unit tests
- unpack it and run an MCP entrypoint check

Related docs and scripts:

- [docs/v2-release-and-install.md](./docs/v2-release-and-install.md)
- [scripts/build-v2-release.py](./scripts/build-v2-release.py)
- [scripts/verify-v2-release-package.py](./scripts/verify-v2-release-package.py)

What this currently proves:

- a user can receive the zip bundle, unpack it, and successfully run the current V2

What it is not yet:

- a native installer
- a pip package
- a one-click MCP client installation flow

## Suggested Reading Order

If this is your first time in the repo, read in this order:

1. [docs/v2-status.md](./docs/v2-status.md)
2. [docs/v2-how-to-command-gpf.md](./docs/v2-how-to-command-gpf.md)
3. [docs/v2-natural-language-boundary-principles.md](./docs/v2-natural-language-boundary-principles.md)
4. [docs/v2-basic-flow-user-intent.md](./docs/v2-basic-flow-user-intent.md)
5. [docs/v2-basic-flow-staleness-and-generation.md](./docs/v2-basic-flow-staleness-and-generation.md)
6. [docs/v2-plugin-runtime-map.md](./docs/v2-plugin-runtime-map.md)

If you only want to use the project rather than extend it, prioritize:

1. [docs/v2-status.md](./docs/v2-status.md)
2. [docs/v2-how-to-command-gpf.md](./docs/v2-how-to-command-gpf.md)

## Branch Layout

The current repository convention is:

- `main`: the actively maintained Pointer GPF V2 branch
- `legacy/mcp`: the preserved old system for reference only

If you need the old implementation, inspect `legacy/mcp`, but do not merge legacy system behavior back into `main`.
