# 2026-04-27 GPF Agent-Controlled Sustainable Development Plan

## Purpose

This document turns the current GPF product vision into a long-running development plan that an agent can continue without repeatedly stopping to ask what to do next.

Target product scenario:

1. A user installs GPF into a Godot project.
2. The user uses Codex, Cursor, or another AI coding tool.
3. The user describes a game bug in natural language.
4. The language model and GPF work together to understand, inspect, reproduce, observe, locate, fix, verify, and report the bug.
5. GPF acts as an automated gray-box testing and debug tool during AI-assisted game development.

Current product truth:

- GPF already has real `play_mode` execution, bounded natural-language routing, runtime evidence primitives, bug repro artifacts, bounded fix proposals, rerun, regression, and real-bug round infrastructure.
- The main missing product behavior is not another fixed bug type. The main missing behavior is reliable model-driven evidence planning and model-driven bounded edit proposals from real project facts.
- GPF is not the component that should understand every game's rules, controls, or repair strategy by itself. Codex, Cursor, or another AI coding tool should do the project-specific reasoning and generate the evidence plan, operation plan, and fix proposal.
- GPF should provide the AI tool with structured project facts, available action contracts, evidence schemas, validation rules, execution results, and artifact paths so the model can reason within a clear framework.
- Without a language model, GPF has no realistic path to become a gray-box tester that covers every game type, every gameplay system, and every control scheme. The scalable product path is context injection plus bounded execution: GPF supplies the model with the project context and tool contracts, then the model decides what must be analyzed and what plan should be generated for that specific project.

This document is the active development control document for that target.

## Agent Operating Rule

When continuing work from this document, the agent should run as far as possible without asking for permission between small steps.

Default behavior:

1. Read current status documents.
2. Verify the current baseline.
3. Pick the highest-priority unfinished work package in this document.
4. Implement code, tests, docs, and verification together.
5. Write artifacts into repo or test-project files.
6. Continue to the next work package when the previous one is verified.

The agent should ask the user only when one of these is true:

- a destructive operation would modify files outside `D:\AI\pointer_gpf` or `D:\AI\pointer_gpf_testgame`
- credentials, account access, billing, or external publishing is required
- two user-visible product directions conflict and the repo has no recorded decision
- a real Godot editor/runtime condition cannot be resolved automatically after reading `pointer_gpf/tmp/runtime_diagnostics.json` when it exists

Everything else should be handled by the agent through code inspection, controlled test-project changes, commands, and repo documentation.

## Mandatory Start Sequence

Every new development run that uses this document must begin with these files:

1. `AGENTS.md`
2. `.cursor/rules/global-communication-terminology.mdc`
3. `.cursor/rules/gpf-runtime-test-mandatory-play-mode.mdc`
4. `docs/v2-status.md`
5. `docs/v2-handoff.md`
6. `docs/v2-how-to-command-gpf.md`
7. `docs/2026-04-23-gpf-current-version-summary.md`
8. this document

Then run:

```powershell
python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"
python -m v2.mcp_core.server --tool preflight_project --project-root D:\AI\pointer_gpf_testgame
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\basic_minimal_flow.json
```

For larger work packages, also run:

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame
```

Rules:

- Run flow commands serially against `D:\AI\pointer_gpf_testgame`.
- Do not overlap two Godot runtime flows against the same target project.
- If a flow fails, inspect `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\runtime_diagnostics.json` when it exists before reporting inability to continue.
- Do not report success unless the relevant command output has been observed.

## Development Ledger

Long-running progress should not live only in chat.

Use these files:

- this file: durable plan and current work queue
- `docs/v2-status.md`: current implementation state and verification status
- `docs/v2-handoff.md`: restart context for a new conversation
- `docs/2026-04-23-gpf-current-version-summary.md`: current product snapshot until a newer summary replaces it
- `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\bug_dev_rounds\<round_id>\`: real-bug round artifacts

When a work package finishes, update at least:

1. the relevant implementation docs
2. `docs/v2-status.md`
3. `docs/v2-handoff.md`

If the work changes user-facing behavior, also update:

1. `README.md`
2. `README.en.md`
3. `docs/v2-how-to-command-gpf.md`

## Product Architecture Target

The desired product architecture is:

1. Natural-language bug request enters the AI tool.
2. The AI tool calls GPF to collect structured project facts.
3. The AI tool generates a bounded evidence plan.
4. GPF validates the evidence plan.
5. GPF runs real `play_mode` actions and records runtime evidence.
6. The AI tool generates a bounded fix proposal from GPF evidence.
7. GPF validates and applies the edit.
8. GPF reruns the same bug-focused repro.
9. GPF runs regression.
10. GPF reports one final status with artifact paths.

Division of responsibility:

- the language model chooses what to inspect, how to understand the target project, what operation sequence to try, what evidence to collect, and what edit to propose
- GPF exposes the available action vocabulary, evidence vocabulary, project facts, validation errors, execution artifacts, and result classifications that make that model reasoning concrete
- GPF validates model-provided plans, performs bounded runtime execution, writes artifacts, applies only accepted edits, and verifies results
- the repo stores enough evidence for another agent or developer to review the result

GPF must not become:

- an open-domain natural-language automation system
- a growing list of one-off bug handlers
- a catalog of game-genre-specific operation strategies
- the component that guesses a project's controls, gameplay intent, or repair plan without a model-provided plan
- a tool that edits files without evidence and rerun
- a tool that reports success from model text alone

## Product Boundary Correction: Model-First Project Reasoning

This section supersedes any wording in this document that implies GPF itself should grow toward a project-specific or genre-specific gameplay operator.

GPF's durable product role:

1. expose structured project context for model use
2. expose a bounded action and evidence schema
3. validate model-generated evidence plans and fix proposals
4. run accepted plans in real `play_mode`
5. persist compact evidence and diagnostics
6. classify results in a way the model and user can review

The AI coding tool's role:

1. read the user's natural-language bug report
2. interpret the target project's code, scenes, controls, and intended behavior
3. decide which GPF tools to call
4. generate the project-specific evidence plan
5. generate the project-specific fix proposal
6. explain the final result to the user using GPF artifacts

The external test project is only an evaluation target. It is allowed to contain concrete mechanics such as a moving triangle enemy, but those mechanics must be used to test general contracts: whether GPF exposes enough facts, accepts a model-generated plan, runs it faithfully, records evidence, and reports the result. They must not become hard-coded assumptions in GPF.

The test for this product boundary is simple: when a new project has unfamiliar code, unfamiliar game design, or unfamiliar operation rules, GPF should not try to guess a universal workflow. It should expose enough context for the model to understand what must be inspected, which runtime facts matter, which player or system actions are available, and which evidence would prove or disprove the reported bug.

When planning future work, phrase it as a model-facing support improvement, for example:

- improve the project context payload that helps the model infer controls
- improve the evidence-plan schema and rejection messages
- improve artifacts that explain what happened during a run
- improve validation that catches invalid or unsafe model proposals

Do not phrase future work as:

- teach GPF how to solve this specific test game
- teach GPF a fixed strategy for one genre
- add project-specific behavior that bypasses the model's reasoning step

## Work Package A: Product Installation And AI Tool Entry

### Goal

Make a new project installation path that can be followed by a user or AI tool without reading implementation internals.

### Files

- `docs/v2-release-and-install.md`
- `scripts/build-v2-release.py`
- `scripts/verify-v2-release-package.py`
- `README.md`
- `README.en.md`
- optional: `docs/v2-ai-tool-integration.md`

### Implementation Tasks

1. Add a verified install walkthrough for a fresh Godot project.
2. Add Codex and Cursor MCP configuration examples if they can be expressed without secrets.
3. Add a command that verifies an installed target project can call:
   - `get_user_request_command_guide`
   - `preflight_project`
   - `run_basic_flow`
4. Add release-package verification that exercises the same path.

### Acceptance

- A fresh unpacked package can run unit tests and at least one MCP command.
- A target project can sync the plugin, pass preflight, and run the minimal flow.
- Docs state exactly what the user copies or runs.

### Verification

```powershell
python D:\AI\pointer_gpf\scripts\build-v2-release.py
python D:\AI\pointer_gpf\scripts\verify-v2-release-package.py --package <zip>
python -m v2.mcp_core.server --tool get_user_request_command_guide --project-root D:\AI\pointer_gpf_testgame
python -m v2.mcp_core.server --tool preflight_project --project-root D:\AI\pointer_gpf_testgame
```

## Work Package B: Behavior-Bug Static Observation

Status: first implementation slice completed on 2026-04-27.

### Goal

Give the language model enough project facts to reason about behavior bugs such as hit feedback, animation feedback, shader feedback, state transition, and signal-driven UI updates.

### Files

- `v2/mcp_core/bug_observation.py`
- optional new helper: `v2/mcp_core/project_static_observation.py`
- optional new helper: `v2/mcp_core/godot_scene_index.py`
- `v2/tests/test_bug_observation.py`

### Implementation Tasks

1. Index scenes and scripts referenced from the startup path and bug location hints.
2. Extract candidate nodes by name, type, group, script, and scene path.
3. Extract signal connection facts from `.tscn` files.
4. Extract likely behavior methods from `.gd` files:
   - `take_damage`
   - `damage`
   - `hit`
   - `hurt`
   - `flash`
   - `feedback`
   - `animation`
   - `shader`
5. Extract likely visual state surfaces:
   - `modulate`
   - `self_modulate`
   - `material`
   - `ShaderMaterial`
   - `AnimationPlayer`
   - `Tween`
6. Add a compact observation payload for model use.

### Acceptance

- For the external test project, `observe_bug_context` returns candidate files and candidate runtime evidence targets for behavior bugs.
- The payload stays bounded and does not dump whole files.
- Candidate facts include paths that actually exist in the project.

### Implemented First Slice

Implemented in `v2/mcp_core/bug_observation.py`:

- `project_static_observation` payload inside `observe_bug_context`
- candidate project files from startup scene, basicflow files, bug location hints, bug text tokens, and first-level resource references
- candidate script behavior methods such as hit, damage, flash, feedback, shader, and animation methods
- candidate scene nodes such as enemy, sprite, mesh, and animation-related nodes
- scene signal connection extraction
- visual state surface extraction for shader params, material terms, `modulate`, `AnimationPlayer`, and related feedback terms
- runtime evidence target candidates for sprite property sampling, shader parameter sampling, animation state sampling, and signal observation

Verification performed:

- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_observation.py` -> `Ran 1 test`, `OK`
- `python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"` -> `Ran 199 tests`, `OK`
- `python -m v2.mcp_core.server --tool observe_bug_context --project-root D:\AI\pointer_gpf_testgame --bug-report "敌人受击后没有闪红" --expected-behavior "敌人受击后应该闪红一次并恢复" --steps-to-trigger "启动游戏|让敌人受击" --location-node Enemy` returned `ok: true` and included `res://scripts/enemies/test_enemy.gd`, `_apply_hit_effect`, `Sprite3D`, `hit_count`, and `runtime_evidence_target_candidates`.

### Verification

```powershell
python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_observation.py
python -m v2.mcp_core.server --tool observe_bug_context --project-root D:\AI\pointer_gpf_testgame --bug-report "敌人受击后没有闪红" --expected-behavior "敌人受击后应该闪红一次并恢复" --steps-to-trigger "启动游戏|让敌人受击" --location-node Enemy
```

## Work Package C: Runtime Evidence For Behavior Bugs

Status: first implementation slice completed on 2026-04-27; real hit-feedback trigger evidence is now implemented; remaining work is restore checks and model-generated evidence plans.

### Goal

Support time-window evidence that can prove a visible or stateful behavior changed, did not change, or failed to restore.

### Files

- `v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd`
- `v2/mcp_core/contracts.py`
- `v2/mcp_core/flow_runner.py`
- `v2/mcp_core/runtime_orchestration.py`
- `v2/mcp_core/bug_repro_execution.py`
- `v2/tests/test_flow_runner.py`
- `v2/tests/test_runtime_orchestration.py`

### Implementation Tasks

1. Extend `sample` support for:
   - `node_property`
   - `shader_param`
   - `animation_state`
   - `signal_connection_exists`
2. Extend `observe` support for:
   - scene changes
   - animation events
   - signal emissions
3. Add evidence predicates:
   - changed within window
   - equals at least once
   - returns to baseline
   - event emitted
   - animation played
4. Persist compact evidence records in flow reports and bug repro results.
5. Keep evidence records small enough for model context.

### Acceptance

- A real `play_mode` flow can prove at least one property timeline.
- A real `play_mode` flow can prove at least one event window.
- A check can reference evidence by id.

### Implemented First Slice

Implemented in `v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd`:

- evidence predicate `value_seen`
- evidence predicate `equals_at_least_once`
- evidence predicate `sample_value_equals`
- evidence predicate `first_value_equals`
- evidence predicate `last_value_equals`
- numeric predicate comparison now treats integer and float representations of the same value as equal
- `shader_param` sampling now supports both `CanvasItem.material` and `GeometryInstance3D.material_override`
- bounded runtime action `callMethod`, which resolves a target node, calls a named method with JSON-coerced arguments, and returns a serialized result
- `callMethod` argument coercion for `Vector2`, `Vector3`, `Color`, and `node_global_position`
- bounded runtime action `aimAt`, which sends equivalent mouse motion so a player controller rotates toward a 3D target node
- bounded runtime action `shoot`, which sends a left mouse button input event through the player controller path

Added `v2/flows/runtime_evidence_value_predicate_flow.json`.
Added `v2/flows/runtime_evidence_shader_param_flow.json`.
Added `v2/flows/runtime_evidence_hit_feedback_flow.json`.

Updated `scripts/verify-v2-regression.py` so the fixed regression bundle now runs the value-predicate flow, the 3D shader-parameter flow, and the hit-feedback behavior flow.

Verification performed:

- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_flow_runner.py D:\AI\pointer_gpf\v2\tests\test_runtime_orchestration.py` -> `Ran 16 tests`, `OK`
- `python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_value_predicate_flow.json` -> `ok: true`, `execution.status: passed`, `runtime_evidence_summary.record_count: 1`, sampled `StartButton.visible=true`
- `python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_shader_param_flow.json` -> `ok: true`, `execution.status: passed`, `runtime_evidence_summary.record_count: 1`, sampled `/root/GameLevel/TestEnemy/Sprite3D` shader `hit_count=0`
- `python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_hit_feedback_flow.json` -> `ok: true`, `execution.status: passed`, `runtime_evidence_summary.record_count: 2`, sampled shader `hit_count=0`, aimed `FPSController` at `Sprite3D`, fired a left mouse click, then sampled `hit_count=1`
- `python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"` -> `Ran 199 tests`, `OK`
- `python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame` -> `ok: true`, includes `runtime_evidence_value_predicate_flow`, `runtime_evidence_shader_param_flow`, and `runtime_evidence_hit_feedback_flow`

### Verification

```powershell
python -m unittest D:\AI\pointer_gpf\v2\tests\test_flow_runner.py D:\AI\pointer_gpf\v2\tests\test_runtime_orchestration.py
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_sample_flow.json
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_observe_flow.json
```

## Work Package D: Model Evidence Plan Automation

Status: contract documentation slice completed on 2026-04-27. Model evidence plans can now include bounded `callMethod`, `aimAt`, and `shoot` trigger steps. The hit-feedback example now drives shooting through player input instead of directly invoking the enemy hit method, and the model-facing schema has a dedicated contract document plus multiple accepted examples.

### Goal

Make the AI tool able to turn a GPF observation payload into a valid evidence plan without user hand-editing JSON.

### Files

- `v2/mcp_core/bug_evidence_plan.py`
- `v2/mcp_core/bug_repro_flow.py`
- `v2/tests/test_bug_evidence_plan.py`
- `v2/tests/test_bug_repro_flow.py`
- `docs/v2-how-to-command-gpf.md`
- optional: `docs/v2-model-evidence-plan-contract.md`

### Implementation Tasks

1. Document the exact JSON schema the model should emit.
2. Add examples for:
   - scene transition bug
   - missing HUD bug
   - hit feedback bug
   - animation feedback bug
   - shader feedback bug
3. Improve rejection messages so the model can self-correct.
4. Make `repair_reported_bug` result include a compact model instruction when `status` is `awaiting_model_evidence_plan`.
5. Add tests for accepted and rejected evidence plans.

### Acceptance

- `repair_reported_bug` returns enough information for the AI tool to generate the next evidence plan.
- Invalid evidence plans are rejected with one or more precise reasons.
- Valid evidence plans are inserted into repro candidate flows.

### Implemented First Repair-Driver Slice

Implemented in `v2/mcp_core/bug_evidence_plan.py` and `v2/mcp_core/bug_repro_flow.py`:

- model evidence plans now accept `callMethod`, `aimAt`, and `shoot` actions as bounded trigger steps
- accepted `callMethod` entries are normalized back to the flow action name `callMethod`
- `callMethod` plan validation requires a target object, method name, and array args
- `aimAt` plan validation requires a target object and accepts an optional player object
- `shoot` plan validation accepts an optional player object
- model evidence plans can now carry the full hit-feedback repro sequence without a fixed per-bug planner branch
- when a model evidence plan is accepted, older heuristic assertions remain as planning context but are not inserted as blocking runtime steps ahead of the model-specified trigger sequence

Implemented in `v2/mcp_core/bug_repair_workflow.py`:

- when `repair_reported_bug` returns `awaiting_model_evidence_plan`, the payload now includes `model_evidence_plan_instruction`
- the instruction payload includes the expected schema, allowed actions, allowed phases, bounded limits, bug context, project fact hints, previous rejection reasons, and a compact example plan
- `observe_bug_context` runtime evidence capabilities now include `callMethod`

Added example artifact:

- `v2/examples/hit_feedback_evidence_plan.json`
- `v2/examples/scene_transition_evidence_plan.json`
- `v2/examples/hud_spawn_evidence_plan.json`
- `v2/examples/animation_feedback_evidence_plan.json`
- `v2/examples/shader_feedback_evidence_plan.json`

Added contract document:

- `docs/v2-model-evidence-plan-contract.md`

Verification performed:

- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_evidence_plan.py D:\AI\pointer_gpf\v2\tests\test_bug_repro_flow.py` -> `Ran 14 tests`, `OK`
- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_repair_workflow.py` -> `Ran 4 tests`, `OK`
- `python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame --bug-report "敌人受击后没有闪红" --expected-behavior "敌人受击后应该闪红一次" --steps-to-trigger "启动游戏|让敌人受击" --location-node Enemy` -> `ok: true`, `status: awaiting_model_evidence_plan`, returned `model_evidence_plan_instruction` with `callMethod`
- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_evidence_plan.py D:\AI\pointer_gpf\v2\tests\test_bug_fix_proposal.py` -> `Ran 11 tests`, `OK`
- `python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"` -> `Ran 206 tests`, `OK`
- `python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame` -> `ok: true`

### Verification

```powershell
python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_evidence_plan.py D:\AI\pointer_gpf\v2\tests\test_bug_repro_flow.py
python -m v2.mcp_core.server --tool plan_bug_repro_flow --project-root D:\AI\pointer_gpf_testgame --bug-report "敌人受击后没有闪红" --expected-behavior "敌人受击后应该闪红一次并恢复" --steps-to-trigger "启动游戏|让敌人受击" --location-node Enemy --evidence-plan-json "<json>"
```

## Work Package E: Behavior-Bug Real Round

Status: first real behavior-bug round completed on 2026-04-27 for `hit_feedback_shader_not_updated`; this case has also been routed through `repair_reported_bug` with model evidence and fix proposal files.

### Goal

Validate the generic workflow against a real behavior bug in the test project.

### Files

- `v2/mcp_core/test_project_bug_seed.py`
- `v2/mcp_core/test_project_bug_round.py`
- `v2/mcp_core/test_project_bug_restore.py`
- `v2/tests/test_test_project_bug_seed.py`
- artifacts under `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\bug_dev_rounds\<round_id>\`

### Required Bug Case

Use a real injected behavior bug such as:

- enemy receives hit but red flash never starts
- red flash starts but never returns to normal
- animation name mismatch prevents feedback
- shader parameter name mismatch prevents feedback
- signal is emitted but visual feedback method is disconnected

Implemented bug kind:

- `hit_feedback_shader_not_updated`: inserts an early return into `_sync_hits_to_shader()` in `res://scripts/enemies/test_enemy.gd`, so `_on_bullet_hit()` can still run but shader `hit_count` remains unchanged.

### Mandatory Sequence

1. Record baseline files before injection.
2. Write bug injection plan.
3. Inject the real bug into project files.
4. Write bug case file.
5. Run repro in real `play_mode`.
6. Persist runtime evidence.
7. Apply bounded fix proposal.
8. Rerun the same bug-focused flow.
9. Run regression.
10. Restore baseline.
11. Verify restored project.

### Acceptance

- The bug exists in real project content.
- Repro evidence points to actual runtime state.
- The fix is applied through the same public bounded proposal workflow.
- Restore result is written and verified.

### Verification

```powershell
python -m v2.mcp_core.server --tool seed_test_project_bug --project-root D:\AI\pointer_gpf_testgame --bug-kind <kind> --bug-report "<report>" --expected-behavior "<expected>" --steps-to-trigger "<steps>" --location-scene <scene> --location-node <node> --location-script <script>
python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame --bug-report "<report>" --expected-behavior "<expected>" --steps-to-trigger "<steps>" --location-node <node> --evidence-plan-file <file> --fix-proposal-file <file>
python -m v2.mcp_core.server --tool restore_test_project_bug_round --project-root D:\AI\pointer_gpf_testgame --round-id <round_id>
```

### Implemented First Round

Implemented in `v2/mcp_core/test_project_bug_seed.py`:

- supported injected bug kind `hit_feedback_shader_not_updated`
- mutation marker `gpf_seeded_bug:hit_feedback_shader_not_updated`
- expected verification target for a reproduced behavior bug where the hit method runs but shader `hit_count` remains unchanged
- fixed the shared function-entry injection regex so inserted returns do not create an extra blank line after the function signature

Added coverage in `v2/tests/test_test_project_bug_seed.py`.

Real test project round:

- round id: `20260427-185421-919628`
- bug id: `hit_feedback_shader_not_updated-185421`
- bug source: injected in this run
- affected files recorded by the round:
  - `scripts/enemies/test_enemy.gd`
  - `scenes/game_level.tscn`
- baseline manifest: `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\bug_dev_rounds\20260427-185421-919628\baseline_manifest.json`
- bug injection plan: `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\bug_dev_rounds\20260427-185421-919628\bug_injection_plan.json`
- restore plan: `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\bug_dev_rounds\20260427-185421-919628\restore_plan.json`
- bug case: `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\bug_dev_rounds\20260427-185421-919628\bug_cases\hit_feedback_shader_not_updated-185421.json`

Verification performed:

- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_test_project_bug_seed.py` -> `Ran 5 tests`, `OK`
- `python -m v2.mcp_core.server --tool seed_test_project_bug --project-root D:\AI\pointer_gpf_testgame --bug-kind hit_feedback_shader_not_updated ...` -> `ok: true`, `status: bug_seeded`
- `python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame --flow-file D:\AI\pointer_gpf\v2\flows\runtime_evidence_hit_feedback_flow.json` while the bug was injected -> `ok: false`, failed at `check_enemy_hit_count_after_one`; report `flow_run_report_0e464fa3904c4b27b12dd365819bc5d9.json` sampled `enemy_hit_count_after` as `0, 0, 0, 0`
- `python -m v2.mcp_core.server --tool restore_test_project_bug_round --project-root D:\AI\pointer_gpf_testgame --round-id 20260427-185421-919628` wrote `restore_result.json` with `status: restored_and_verified`, restored both recorded files, and ran fixed regression with return code `0`
- restore command note: the local shell call timed out because full fixed regression exceeded the 120 second command timeout; `restore_result.json` confirms the restore and verification completed
- post-restore direct verification with `runtime_evidence_hit_feedback_flow.json` -> `ok: true`, `execution.status: passed`, `runtime_evidence_summary.record_count: 2`, after-hit samples were `hit_count=1`

### Implemented Repair-Driver Round

Real test project round:

- round id: `20260427-191248-387259`
- bug id: `hit_feedback_shader_not_updated-191248`
- bug source: injected in this run
- affected files recorded by the round:
  - `scripts/enemies/test_enemy.gd`
  - `scenes/game_level.tscn`
- evidence plan file: `D:\AI\pointer_gpf\v2\examples\hit_feedback_evidence_plan.json`
- fix proposal file: `D:\AI\pointer_gpf\v2\examples\hit_feedback_fix_proposal.json`
- bug case: `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\bug_dev_rounds\20260427-191248-387259\bug_cases\hit_feedback_shader_not_updated-191248.json`

Verification performed:

- `python -m v2.mcp_core.server --tool seed_test_project_bug --project-root D:\AI\pointer_gpf_testgame --bug-kind hit_feedback_shader_not_updated ...` -> `ok: true`, `status: bug_seeded`
- `python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame ... --evidence-plan-file D:\AI\pointer_gpf\v2\examples\hit_feedback_evidence_plan.json --fix-proposal-file D:\AI\pointer_gpf\v2\examples\hit_feedback_fix_proposal.json` -> `ok: true`, `status: fixed_and_verified`, `blocking_point: ""`, `next_action: ""`
- repair artifacts were written to:
  - `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\last_bug_repro_result.json`
  - `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\last_bug_fix_proposal.json`
  - `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\last_bug_fix_application.json`
  - `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\last_bug_fix_verification.json`
  - `D:\AI\pointer_gpf_testgame\pointer_gpf\tmp\last_bug_fix_regression.json`
- `python -m v2.mcp_core.server --tool restore_test_project_bug_round --project-root D:\AI\pointer_gpf_testgame --round-id 20260427-191248-387259` -> `ok: true`, `status: restored_and_verified`, restored `scenes/game_level.tscn` and `scripts/enemies/test_enemy.gd`
- `Select-String -Path D:\AI\pointer_gpf_testgame\scripts\enemies\test_enemy.gd -Pattern 'gpf_seeded_bug:hit_feedback_shader_not_updated' -SimpleMatch` -> no match

## Work Package F: Model Fix Proposal Automation

Status: contract documentation slice completed on 2026-04-27. A bounded model fix proposal example can remove the injected hit-feedback bug through the public proposal/application path, and the model-facing schema now has a dedicated contract document plus safe and rejected examples.

### Goal

Make the AI tool able to generate a valid bounded fix proposal from GPF evidence and fix-plan output.

### Files

- `v2/mcp_core/bug_fix_planning.py`
- `v2/mcp_core/bug_fix_proposal.py`
- `v2/mcp_core/bug_fix_application.py`
- `v2/tests/test_bug_fix_planning.py`
- `v2/tests/test_bug_fix_proposal.py`
- `v2/tests/test_bug_fix_application.py`
- optional: `docs/v2-model-fix-proposal-contract.md`

### Implementation Tasks

1. Ensure `plan_bug_fix` ranks candidate files with evidence reasons.
2. Add a model-facing fix proposal schema and examples.
3. Improve rejection reasons:
   - candidate file not in fix plan
   - unsupported file suffix
   - edit text missing
   - edit text not unique
   - proposal too broad
4. Persist proposed change summary before applying edits.
5. Persist application result after edits.

### Acceptance

- The AI tool can generate a bounded proposal without user hand-editing JSON.
- GPF rejects unsafe or vague proposals.
- Accepted edits are followed by rerun and regression.

### Implemented First Repair-Driver Slice

Added example artifact:

- `v2/examples/hit_feedback_fix_proposal.json`
- `v2/examples/fix_proposal_safe_replace_example.json`
- `v2/examples/fix_proposal_rejected_candidate_mismatch_example.json`
- `v2/examples/fix_proposal_rejected_broad_edit_example.json`

Added contract document:

- `docs/v2-model-fix-proposal-contract.md`

The proposal targets `res://scripts/enemies/test_enemy.gd` and removes the injected marker line:

- `return  # gpf_seeded_bug:hit_feedback_shader_not_updated`

Implemented in `v2/mcp_core/bug_repair_workflow.py`:

- when `repair_reported_bug` returns `bug_reproduced_awaiting_fix_proposal`, the payload now includes `model_fix_proposal_instruction`
- the instruction payload includes the expected schema, fix constraints, candidate files, fix goals, acceptance checks, runtime evidence summary, and a compact replace-edit example

Verification performed in round `20260427-191248-387259`:

- `repair_reported_bug` loaded the proposal file
- `apply_bug_fix` produced `last_bug_fix_application.json`
- bug-focused rerun passed
- fixed regression passed
- final repair status was `fixed_and_verified`
- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_repair_workflow.py` -> `Ran 4 tests`, `OK`
- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_evidence_plan.py D:\AI\pointer_gpf\v2\tests\test_bug_fix_proposal.py` -> `Ran 11 tests`, `OK`

### Verification

```powershell
python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_fix_planning.py D:\AI\pointer_gpf\v2\tests\test_bug_fix_proposal.py D:\AI\pointer_gpf\v2\tests\test_bug_fix_application.py
python -m v2.mcp_core.server --tool apply_bug_fix --project-root D:\AI\pointer_gpf_testgame --fix-proposal-file <file>
```

## Work Package G: Top-Level Repair Driver

Status: repair-summary slice completed on 2026-04-27. `repair_reported_bug` can now reach `fixed_and_verified` for the injected hit-feedback behavior bug when supplied with model evidence and bounded fix proposal files, and result payloads now include structured artifact and repair summaries.

### Goal

Make `repair_reported_bug` able to coordinate the whole sequence when the AI tool supplies required model artifacts.

### Files

- `v2/mcp_core/bug_repair_workflow.py`
- `v2/mcp_core/tool_dispatch.py`
- `v2/mcp_core/server.py`
- `v2/mcp_core/request_layer.py`
- `v2/tests/test_bug_repair_workflow.py`
- `v2/tests/test_tool_dispatch.py`
- `v2/tests/test_server.py`

### Implementation Tasks

1. Keep stop statuses explicit:
   - `awaiting_model_evidence_plan`
   - `bug_reproduced_awaiting_fix_proposal`
   - `fix_applied_awaiting_repro_success`
   - `regression_failed`
   - `fixed_and_verified`
2. Add artifact paths to each stop status.
3. Add compact instructions for the AI tool's next action.
4. Ensure rerun uses the same bug-focused evidence expectations.
5. Ensure regression runs only after bug-focused rerun passes.

### Acceptance

- One explicit bug request can reach final status when evidence and fix proposal are supplied.
- Failure states include `blocking_point`, `next_action`, and artifact paths.
- Success state includes applied changes and verification summary.

### Implemented First End-To-End Slice

Validated on real round `20260427-191248-387259`:

- bug source: injected in this run
- `repair_reported_bug` accepted the evidence plan and fix proposal files
- repro classified the injected failure from runtime evidence
- fix application removed the injected return in the test project
- rerun verified shader `hit_count` changed from `0` to `1`
- regression passed before the tool returned success
- final status: `fixed_and_verified`
- restore status after the round: `restored_and_verified`

Known note from the earlier round `20260427-190535-980668`:

- one previous repair attempt reached the fix/rerun path but ended with `regression_failed` because the hit-feedback flow timed out during `close_project`
- the same flow was then rerun directly and passed, and the later round `20260427-191248-387259` completed with final status `fixed_and_verified`

### Implemented Repair-Summary Slice

Implemented in `v2/mcp_core/bug_repair_workflow.py`:

- `artifact_summary`
  - `files`: deduplicated artifact paths
  - `by_stage`: stage-labeled paths for repro, proposal, application, rerun, and regression artifacts
- `repair_summary`
  - bug source, round id, bug id, and injected bug kind when available
  - repro status, failed phase, failed check ids, runtime evidence ids, and repro artifact path
  - fix-plan status, candidate files, and fix goals
  - apply status, applied changes, proposal artifact, and application artifact
  - rerun status, runtime evidence ids, and rerun artifact path
  - regression status and regression artifact path

Verification performed:

- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_repair_workflow.py` -> `Ran 4 tests`, `OK`
- `python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"` -> `Ran 206 tests`, `OK`
- `python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame --bug-report "敌人受击后没有闪红" --expected-behavior "敌人受击后应该闪红一次" --steps-to-trigger "启动游戏|让敌人受击" --location-node Enemy` -> `ok: true`, `status: awaiting_model_evidence_plan`

### Verification

```powershell
python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_repair_workflow.py D:\AI\pointer_gpf\v2\tests\test_tool_dispatch.py D:\AI\pointer_gpf\v2\tests\test_server.py
python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame --bug-report "<report>" --expected-behavior "<expected>" --steps-to-trigger "<steps>" --location-node <node> --evidence-plan-file <file> --fix-proposal-file <file>
```

## Work Package H: Final User Report

Status: real CLI validation slice completed on 2026-04-27. `repair_reported_bug` now returns a structured `user_report` after repro has run, and a real injected-bug round confirmed that `user_report` appears in CLI output.

### Goal

Turn repair artifacts into a concise user-facing report.

### Files

- optional new helper: `v2/mcp_core/repair_report_formatter.py`
- `v2/mcp_core/bug_repair_workflow.py`
- `v2/tests/test_repair_report_formatter.py`
- `docs/v2-how-to-command-gpf.md`

### Report Must Include

- bug summary
- bug source: pre-existing or injected
- repro result
- key runtime evidence ids
- changed files
- rerun result
- regression result
- restore status when a test-project round was used
- final status
- artifact paths

### Acceptance

- The report is understandable without reading raw JSON first.
- Every claim maps to an artifact or command result.
- The report does not hide failure states.

### Implemented First Slice

Implemented in `v2/mcp_core/repair_report_formatter.py` and `v2/mcp_core/bug_repair_workflow.py`:

- `user_report.schema: pointer_gpf.v2.user_repair_report.v1`
- `user_report.sections.bug` contains bug summary, source, round id, and bug id
- `user_report.sections.repro` contains repro status, failed check ids, runtime evidence ids, and repro artifact
- `user_report.sections.fix` contains candidate files, fix goals, apply status, changed files, proposal artifact, and application artifact
- `user_report.sections.verification` contains bug-focused rerun status, rerun artifact, regression status, and regression artifact
- `user_report.markdown` gives a concise text report with artifact references

Verification performed:

- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_repair_report_formatter.py D:\AI\pointer_gpf\v2\tests\test_bug_repair_workflow.py` -> `Ran 5 tests`, `OK`
- `python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"` -> `Ran 207 tests`, `OK`

### Real CLI Validation

Round `20260427-211825-006332`:

- bug source: injected in this run
- bug kind: `hit_feedback_shader_not_updated`
- `repair_reported_bug` returned `user_report.schema: pointer_gpf.v2.user_repair_report.v1`
- `user_report.markdown` included:
  - repro status `bug_reproduced`
  - failed check `model_evidence_check_4_check_enemy_hit_count_after_one`
  - runtime evidence ids `enemy_hit_count_before` and `enemy_hit_count_after`
  - fix application status `fix_applied`
  - changed file `res://scripts/enemies/test_enemy.gd`
  - bug-focused rerun status `bug_not_reproduced`
  - regression artifact path
- final status for that command was `regression_failed`, because fixed regression hit a `close_project` timeout after the bug-focused rerun passed
- direct fixed regression was retried and failed again at another `close_project` timeout in `basicflow_stale_override`; earlier critical shader and hit-feedback flows passed in that retry
- `restore_test_project_bug_round --round-id 20260427-211825-006332` -> `ok: true`, `status: restored_and_verified`, `verification_returncode: 0`
- post-restore marker check found no `gpf_seeded_bug:hit_feedback_shader_not_updated`
- post-restore process check found no remaining Godot process

### Verification

```powershell
python -m unittest D:\AI\pointer_gpf\v2\tests\test_repair_report_formatter.py
python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame --bug-report "<report>" --expected-behavior "<expected>" --steps-to-trigger "<steps>" --location-node <node> --evidence-plan-file <file> --fix-proposal-file <file>
```

## Continuous Validation Matrix

The final product should be validated across these bug families:

| Family | Example | Required Evidence | Required Fix Type |
| --- | --- | --- | --- |
| Scene transition | click start stays on menu | scene/node after trigger | script or signal repair |
| HUD spawn | HUD missing after entering level | node exists after transition | script or scene repair |
| Node naming | expected node path broken | target not found | scene repair |
| Hit feedback | enemy hit does not flash | property/shader/animation timeline | script, animation, or material repair |
| Feedback reset | enemy stays red forever | returns-to-baseline check | script or animation repair |
| Signal behavior | signal emitted but handler missing | signal connection and emission event | signal or script repair |
| Runtime diagnostics | engine error during trigger | diagnostics artifact | script or resource repair |

Minimum release-quality requirement:

- one passing real-bug round per family
- restore verification after every injected bug round
- fixed regression passing after the round

## Priority Queue

Current queue:

1. Model-facing context and contract clarity: make GPF better at returning project facts, action schemas, evidence schemas, validation failures, and artifact summaries that Codex/Cursor can use to generate project-specific plans.
2. Work Package G/H follow-up: handle fixed-regression `close_project` timeout cases where `project_close.status` is already verified, so successful bug-focused repair is not reported as a generic regression failure without clearer classification.
3. Work Package A: install and AI tool entry polish.
4. Work Package B follow-up: refine behavior-bug static observation if the new contract examples expose missing project facts.

Reasoning:

- install polish matters, but the current source-bundle path is already usable for development
- Work Package C already has real hit-feedback runtime evidence
- Work Package E has restored real behavior-bug rounds for `hit_feedback_shader_not_updated`
- the same real behavior bug has passed through `repair_reported_bug` using model evidence and fix proposal artifacts
- model-facing evidence and fix proposal contracts now exist as repo documents with accepted and rejected examples
- `repair_reported_bug` now includes structured `artifact_summary` and `repair_summary`
- `repair_reported_bug` now includes a structured `user_report` and concise markdown after repro has run
- the largest current product gap is now model-facing context and contract clarity: the AI tool still needs stronger reference material from GPF to generate correct evidence plans and fix proposals for unfamiliar projects
- install and AI tool entry polish still matters because GPF must be easy for Codex/Cursor to call in a fresh project
- clearer handling of regression timeout cases still matters because the final user report must map to observed command results without hiding partial success

## Update Rules

When a work package is completed:

1. Change its status in this document from queue item to completed item.
2. Add exact commands and key outputs to `docs/v2-status.md`.
3. Add restart context to `docs/v2-handoff.md`.
4. Update user-facing docs if behavior changed.
5. Leave raw evidence in artifact files instead of pasting long JSON into docs.

## Completion Definition

The long-term product target is complete only when all are true:

1. A fresh project can install and call GPF from an AI tool.
2. A user can describe a real bug in natural language.
3. The AI tool can generate a valid evidence plan from GPF observation.
4. GPF can reproduce the bug in real `play_mode`.
5. GPF can persist evidence that explains why the bug is real.
6. The AI tool can generate a bounded fix proposal from GPF fix planning.
7. GPF can apply the proposal safely.
8. GPF can rerun the same bug-focused flow.
9. GPF can run regression.
10. GPF can report `fixed_and_verified` only from command results and artifacts.

If any of these still requires repeated manual translation by the user, the product target is not complete yet.

## Test Project Feature Update: Irregular Moving Enemy

Status: completed on 2026-04-27. The external test project now treats the triangle enemy as a moving target, and GPF has a real `play_mode` flow that proves the movement through runtime evidence.

### Implemented

- updated `D:\AI\pointer_gpf_testgame\scripts\enemies\test_enemy.gd`
- added randomized orbit state and exports for radius, angular speed, radius-change speed, and retarget timing
- the triangle enemy keeps floating, keeps facing the player, and moves around the player on the horizontal plane with periodically randomized direction, radius, and angular velocity
- added `D:\AI\pointer_gpf_testgame\pointer_gpf\project_context\07-game-design.md`
- updated `D:\AI\pointer_gpf_testgame\pointer_gpf\project_context\index.json` so the game-design note is discoverable
- added `v2/flows/runtime_evidence_enemy_movement_flow.json`
- updated `scripts/verify-v2-regression.py` so the fixed regression bundle runs the enemy movement evidence flow
- updated `runtime_bridge.gd` so sample windows wait through Godot timers instead of `OS.delay_msec()`, allowing `_process(delta)` to advance while samples are collected

### Evidence

- initial movement-flow attempt entered real `play_mode` and closed the project with `project_close.status: verified`, but failed because `TestEnemy.position` stayed fixed during the sample window
- the failed report showed all samples identical at approximately `(5.16, 1.81, 5.54)`, which exposed that `OS.delay_msec()` was blocking game frames during sampling
- after the sampling fix, `runtime_evidence_enemy_movement_flow.json` returned `ok: true`, `execution.status: passed`, `runtime_evidence_summary.record_count: 1`, and `project_close.status: verified`
- the passing movement report sampled `TestEnemy.position` changing from approximately `(4.81, 1.81, 4.54)` to `(5.40, 1.89, 3.72)`
- `runtime_evidence_hit_feedback_flow.json` still returned `ok: true`, `execution.status: passed`, and sampled shader `hit_count=0` before player-input shooting and `hit_count=1` after shooting
- `python -m unittest D:\AI\pointer_gpf\v2\tests\test_flow_runner.py D:\AI\pointer_gpf\v2\tests\test_bug_evidence_plan.py D:\AI\pointer_gpf\v2\tests\test_bug_repro_flow.py` -> `Ran 26 tests`, `OK`
- `python -m unittest discover -s D:\AI\pointer_gpf\v2\tests -p "test_*.py"` -> `Ran 210 tests`, `OK`
- `python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame` -> `ok: true`; includes `runtime_evidence_enemy_movement_flow` with `ok: true`

### Next Effect On The Overall Goal

This makes the evaluation target more useful, but it does not change GPF's product boundary. The point is not to teach GPF a strategy for a moving enemy or a shooting game. The point is to verify that GPF can expose and execute general runtime evidence contracts for behavior that changes over real frames, so an AI coding tool can use those contracts when it generates a project-specific evidence plan.

The next development step should therefore be model-facing: improve the project context, action schema, evidence schema, validation messages, and examples so Codex/Cursor can infer the target project's controls and generate the right operation plan. The moving enemy is only one evaluation case for those contracts.
