# V2 Model Evidence Plan Contract

This document defines the JSON that an AI tool should generate when `repair_reported_bug` returns `status: awaiting_model_evidence_plan`.

The purpose of the evidence plan is to turn a natural-language bug report and `observe_bug_context` facts into a bounded runtime plan that GPF can validate, execute in real `play_mode`, and use as evidence for later repair.

## When To Generate

Generate this JSON after calling:

```powershell
python -m v2.mcp_core.server --tool repair_reported_bug --project-root <project> --bug-report "<bug>" ...
```

If the result is:

- `status: awaiting_model_evidence_plan`
- `next_action: provide_evidence_plan_json_or_file`

then read:

- `model_evidence_plan_instruction`
- `observation.project_static_observation`
- `observation.runtime_evidence_capabilities`
- `repro_plan.rejected_evidence_plan_reasons`

Then provide either:

- `--evidence-plan-json "<json>"`
- `--evidence-plan-file <path>`

## Schema

```json
{
  "schema": "pointer_gpf.v2.model_evidence_plan.v1",
  "description": "Short purpose of this evidence plan.",
  "steps": []
}
```

`steps` must contain at most 12 entries.

Allowed actions:

- `wait`
- `click`
- `sample`
- `observe`
- `callMethod`
- `aimAt`
- `shoot`
- `check`

Allowed phases:

- `pre_trigger`
- `trigger_window`
- `post_trigger`
- `final_check`

Runtime path rule:

- Use Godot hints such as `node_name:StartButton`
- Use `res://` project paths only when needed
- Do not use `D:\...`, `C:\...`, `file://`, `../`, or `..\`

## Action Shapes

### wait

```json
{
  "id": "wait_target",
  "phase": "pre_trigger",
  "action": "wait",
  "until": {
    "hint": "node_exists:StartButton"
  },
  "timeoutMs": 5000
}
```

### click

```json
{
  "id": "click_start",
  "phase": "trigger_window",
  "action": "click",
  "target": {
    "hint": "node_name:StartButton"
  }
}
```

### sample

```json
{
  "id": "sample_hud_visible",
  "phase": "post_trigger",
  "action": "sample",
  "target": {
    "hint": "node_name:GamePointerHud"
  },
  "metric": {
    "kind": "node_property",
    "property_path": "visible"
  },
  "windowMs": 160,
  "intervalMs": 40,
  "evidenceKey": "hud_visible_after_start"
}
```

Rules:

- `target` must be an object
- `metric` must be an object
- `windowMs` must be between 1 and 5000
- `intervalMs` must be at least 16
- `evidenceKey` is required

Common metric shapes:

```json
{"kind": "node_property", "property_path": "visible"}
```

```json
{"kind": "shader_param", "param_name": "hit_count"}
```

### observe

```json
{
  "id": "observe_scene_change",
  "phase": "trigger_window",
  "action": "observe",
  "event": {
    "kind": "scene_changed"
  },
  "windowMs": 1000,
  "evidenceKey": "scene_change_after_start"
}
```

Rules:

- `event` must be an object
- `windowMs` must be between 1 and 5000
- `evidenceKey` is required

### callMethod

```json
{
  "id": "call_enemy_hit",
  "phase": "trigger_window",
  "action": "callMethod",
  "target": {
    "hint": "node_name:TestEnemy"
  },
  "method": "_on_bullet_hit",
  "args": [
    {
      "kind": "node_global_position",
      "target": {
        "hint": "node_name:Sprite3D"
      }
    }
  ]
}
```

Rules:

- `target` must be an object
- `method` is required
- `args` must be a list if present
- Use only methods that are visible from project facts and needed to trigger the reported behavior
- Prefer `aimAt` plus `shoot` for gameplay shooting bugs where the test project has a real player controller and target.

### aimAt

```json
{
  "id": "aim_at_enemy",
  "phase": "trigger_window",
  "action": "aimAt",
  "player": {
    "hint": "node_name:FPSController"
  },
  "target": {
    "hint": "node_name:Sprite3D"
  }
}
```

Rules:

- `target` must be an object resolving to a 3D target node.
- `player` is optional, but should be supplied when the project has a known player node.
- GPF sends equivalent mouse motion so the player controller rotates toward the target.

### shoot

```json
{
  "id": "shoot_enemy",
  "phase": "trigger_window",
  "action": "shoot",
  "player": {
    "hint": "node_name:FPSController"
  },
  "settleMs": 120
}
```

Rules:

- `player` is optional, but should be supplied when the project has a known player node.
- GPF sends a left mouse button input event through the runtime input path.
- Use this after `aimAt` for shooting and hit-feedback bugs.

### check

```json
{
  "id": "check_hud_visible",
  "phase": "final_check",
  "action": "check",
  "checkType": "node_property_value_seen",
  "evidenceRef": "hud_visible_after_start",
  "predicate": {
    "operator": "value_seen",
    "value": true
  }
}
```

Rules:

- Prefer evidence-backed checks with `evidenceRef`
- `evidenceRef` should match an earlier `evidenceKey`
- If the check uses only `hint`, it should be a precondition or a simple runtime presence check

Common predicate operators currently supported by runtime checks:

- `value_seen`
- `equals_at_least_once`
- `sample_value_equals`
- `first_value_equals`
- `last_value_equals`

## Example Files

Accepted examples live under [v2/examples](/D:/AI/pointer_gpf/v2/examples):

- [scene_transition_evidence_plan.json](/D:/AI/pointer_gpf/v2/examples/scene_transition_evidence_plan.json)
- [hud_spawn_evidence_plan.json](/D:/AI/pointer_gpf/v2/examples/hud_spawn_evidence_plan.json)
- [animation_feedback_evidence_plan.json](/D:/AI/pointer_gpf/v2/examples/animation_feedback_evidence_plan.json)
- [shader_feedback_evidence_plan.json](/D:/AI/pointer_gpf/v2/examples/shader_feedback_evidence_plan.json)
- [hit_feedback_evidence_plan.json](/D:/AI/pointer_gpf/v2/examples/hit_feedback_evidence_plan.json)

## Model Generation Rules

Use `observe_bug_context` facts first:

- choose target nodes from `runtime_evidence_target_candidates` or `candidate_nodes`
- choose methods from `behavior_methods`
- choose files from `candidate_files` only for reasoning, not for direct file editing
- choose shader or property names from `visual_state_surfaces`

For each reported bug, the evidence plan should prove one thing:

- the trigger happened
- the expected visible or stateful result did not happen

Do not include the fix in the evidence plan.

Do not add broad waiting steps when a precise runtime target exists.

Do not invent node names that are absent from the observation payload unless the bug report explicitly names them.

## Validation

Run:

```powershell
python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_evidence_plan.py
```

For real project validation, pass the plan into:

```powershell
python -m v2.mcp_core.server --tool plan_bug_repro_flow --project-root D:\AI\pointer_gpf_testgame --bug-report "<bug>" --expected-behavior "<expected>" --steps-to-trigger "<steps>" --location-node <node> --evidence-plan-file <plan.json>
```

Then run the repair path:

```powershell
python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame --bug-report "<bug>" --expected-behavior "<expected>" --steps-to-trigger "<steps>" --location-node <node> --evidence-plan-file <plan.json>
```
