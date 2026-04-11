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

But product language should remember that the user-facing meaning is:

- run the basic test flow

That phrase carries the real intent:

- "show me what GPF can do in my project"
- "prove the project still stands after important changes"
