# V2 Basic Flow User Intent

## Why `run_basic_flow` exists

`run_basic_flow` is not just a technical helper name.

In Pointer GPF product intent, it is the implementation of:

- run the basic test flow

The phrase "basic test flow" means:

- GPF inspects the current game project
- GPF analyzes the current project state
- GPF generates a simplest-possible playable test flow based on its current understanding of the project
- GPF then actually runs that flow in the engine and game

So the value is not only "run a JSON flow".
The real value is:

- understand the project
- decide a minimal meaningful path through the project
- execute that path
- show the user visible proof that GPF can operate the engine and the game

## Real User Scenarios

### Scenario 1: First-time value demonstration

Many users configure the MCP, read the docs, and still do not yet feel what GPF is actually useful for.

The docs alone do not let them directly see:

- that GPF can understand their project
- that GPF can drive their engine
- that GPF can launch and operate the game
- that the red pointer can move and act inside the running game
- that a test flow is not theoretical, but actually runs

For these users, asking GPF to "run the basic test flow" is mainly a value demonstration request.

The expected user feeling is:

- after setup, quickly and clearly see that GPF is real and useful
- see visible engine/game interaction, not just configuration text
- understand "this MCP is not only documentation or static analysis; it can actually do things in my project"

### Scenario 2: Ongoing confidence check for experienced users

Even skilled repeat users still need to ask GPF to "run the basic test flow".

Typical reason:

- they made deep or implicit changes to core systems
- the impact surface may be broad
- they need a quick confidence check before continuing development

In that scenario, passing the basic test flow means:

- at least the project's foundation is still intact
- the core runtime path still works
- they can continue development with a first level of confidence

It is not a full regression suite.
It is a high-value baseline confidence check.

## Product Design Implications

When designing or changing `run_basic_flow`, prefer these product rules:

1. The flow should be as simple as possible, but still visibly meaningful.
2. The result should be understandable to a user who is seeing GPF for the first time.
3. The flow should visibly prove engine control and game interaction, not just background checks.
4. The command should remain useful as a repeatable baseline confidence check for experienced users.
5. Do not reduce it to a purely internal technical primitive with no user-facing meaning.

## Naming Guidance

`run_basic_flow` may stay as an internal or compatibility-oriented tool name if needed.

For V2, the intended rule is:

- keep `run_basic_flow` as the tool / code-facing command name
- treat user language such as "跑基础测试流程" as the natural-language request that maps to `run_basic_flow`
- expose a small structured intent catalog so the upper conversational layer can decide whether the project should:
  - run the saved basicflow now
  - generate the first basicflow
  - analyze why the saved basicflow is stale

But product language should remember that the user-facing meaning is:

- run the basic test flow

That phrase carries the real intent:

- "show me what GPF can do in my project"
- "prove the project still stands after important changes"

## Current V2 Intent Entry

V2 now exposes a small structured entrypoint:

```powershell
python -m v2.mcp_core.server --tool get_basic_flow_user_intents --project-root D:\AI\pointer_gpf_testgame
```

It returns:

- the current `basicflow` state for the project
- one `primary_recommendation` for the upper layer
- a small `secondary_actions` list for nearby alternatives
- the main user intents around basicflow
- which intent is currently recommended or blocked
- the next step the upper user-facing layer should take

This is not a full natural-language router yet.
It is a stable bridge between:

- user-facing intent
- current project state
- existing V2 tool entrypoints

## Current V2 Request Resolution Entry

V2 now also exposes a thin request-resolution entrypoint:

```powershell
python -m v2.mcp_core.server --tool resolve_basic_flow_user_request --project-root D:\AI\pointer_gpf_testgame --user-request "跑基础测试流程"
```

It does two things:

- matches the user request against the current basicflow-related intent catalog
- returns the action that should actually be recommended now for the current project state

The returned shape now also includes a compact decision layer:

- `resolved`
- `tool`
- `reason`
- `requires_confirmation`
- `follow_up_message`

The current phrase coverage is still intentionally small and explicit.
It only targets a short list of high-frequency basicflow requests around:

- run
- generate / regenerate
- analyze staleness / drift

Example:

- if the user says "跑基础测试流程" and the project basicflow is fresh, the recommended action is `run_basic_flow`
- if the user says the same thing but the project basicflow is stale, the recommended action can instead be `generate_basic_flow`

So this entrypoint is the first thin adapter from:

- user-facing phrasing

to:

- current project-aware tool choice

## Current V2 Request Planning Entry

V2 now also exposes a thin planning entrypoint:

```powershell
python -m v2.mcp_core.server --tool plan_basic_flow_user_request --project-root D:\AI\pointer_gpf_testgame --user-request "跑基础测试流程"
```

This goes one step beyond request resolution.
It returns an executable next step for the upper layer, including:

- `tool`
- `args`
- `ready_to_execute`
- `ask_confirmation`
- `message`

Example:

- if the next safe action is still just `run_basic_flow`, the plan returns that tool directly
- if the user wants to regenerate `basicflow`, the plan can return `get_basic_flow_generation_questions` first, because `generate_basic_flow` still needs the 3 answers

## Current Top-Level Planning Entry

V2 now also has a top-level planning entrypoint:

```powershell
python -m v2.mcp_core.server --tool plan_user_request --project-root D:\AI\pointer_gpf_testgame --user-request "跑基础测试流程"
```

Right now it only routes the `basicflow` domain.
It also has a small `project_readiness` slice for:

- `preflight_project`
- `configure_godot_executable`

The goal is:

- keep one top-level planning interface
- let new high-level user request domains plug into it later
- avoid re-solving basicflow-specific state logic in multiple places

## Current Top-Level Handling Entry

V2 now also has a thin execution entrypoint above the planner:

```powershell
python -m v2.mcp_core.server --tool handle_user_request --project-root D:\AI\pointer_gpf_testgame --user-request "run basicflow"
```

This entrypoint does not try to auto-run every possible high-level request.
Right now it only auto-executes the safer next-step tools that do not immediately launch a runtime flow:

- `preflight_project`
- `configure_godot_executable`
- `get_basic_flow_generation_questions`
- `analyze_basic_flow_staleness`

So the current chain is:

- resolve user phrase
- plan the next tool call
- if that next tool is safe to auto-execute, execute it and return the nested result

Example:

- if the user says `run basicflow` on a stale project, `handle_user_request` does not jump straight to `run_basic_flow`
- instead it executes `get_basic_flow_generation_questions` and returns `follow_up_tool: generate_basic_flow`

This keeps the top-level request handling useful without silently starting play-mode execution from every natural-language request.
