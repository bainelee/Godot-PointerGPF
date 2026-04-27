# V2 Model Fix Proposal Contract

This document defines the JSON that an AI tool should generate when `repair_reported_bug` returns `status: bug_reproduced_awaiting_fix_proposal`.

The fix proposal is intentionally bounded. The model may propose small text edits only inside files that GPF has already listed as candidate files in `plan_bug_fix`.

## When To Generate

Generate this JSON after `repair_reported_bug` has:

- reproduced the bug
- written repro evidence
- produced a `fix_plan`
- returned `next_action: provide_fix_proposal_json_or_file`

Read:

- `model_fix_proposal_instruction`
- `fix_plan.candidate_files`
- `fix_plan.fix_goals`
- `fix_plan.acceptance_checks`
- `repro_result.runtime_evidence_summary`
- `repro_result.check_summary`

Then provide either:

- `--fix-proposal-json "<json>"`
- `--fix-proposal-file <path>`

## Schema

```json
{
  "schema": "pointer_gpf.v2.fix_proposal.v1",
  "description": "Short reason for the proposed fix.",
  "candidate_file": "res://scripts/example.gd",
  "edits": []
}
```

Rules:

- `candidate_file` is required
- `candidate_file` must be present in `fix_plan.candidate_files`
- `candidate_file` must end with `.gd` or `.tscn`
- `edits` must be a non-empty list
- `edits` can contain at most 5 entries

Allowed edit kinds:

- `replace_text`
- `insert_after`
- `insert_before`

## Edit Shapes

### replace_text

```json
{
  "kind": "replace_text",
  "find": "\treturn  # incorrect early return\n",
  "replace": ""
}
```

### insert_after

```json
{
  "kind": "insert_after",
  "find": "func _ready():\n",
  "text": "\t_setup_runtime_feedback()\n"
}
```

### insert_before

```json
{
  "kind": "insert_before",
  "find": "func _process(delta):\n",
  "text": "var _feedback_ready := false\n\n"
}
```

Every `find` string must match exactly once in the selected file when GPF applies the proposal.

## Safety Rules

The model should:

- use one candidate file from `fix_plan.candidate_files`
- use the smallest edit that satisfies the failed runtime evidence
- make `find` long enough to be unique
- preserve indentation exactly
- avoid unrelated refactors
- avoid edits to files not listed by GPF

The model should not:

- edit broad text such as `func _process`
- propose an absolute path
- propose a file outside `fix_plan.candidate_files`
- remove large unrelated blocks
- make a change that cannot be verified by the same bug-focused repro

## Example Files

Examples live under [v2/examples](/D:/AI/pointer_gpf/v2/examples):

- [hit_feedback_fix_proposal.json](/D:/AI/pointer_gpf/v2/examples/hit_feedback_fix_proposal.json)
- [fix_proposal_safe_replace_example.json](/D:/AI/pointer_gpf/v2/examples/fix_proposal_safe_replace_example.json)
- [fix_proposal_rejected_candidate_mismatch_example.json](/D:/AI/pointer_gpf/v2/examples/fix_proposal_rejected_candidate_mismatch_example.json)
- [fix_proposal_rejected_broad_edit_example.json](/D:/AI/pointer_gpf/v2/examples/fix_proposal_rejected_broad_edit_example.json)

The rejected examples are intentionally invalid or unsafe. They are included so the AI tool can learn what not to emit.

## Good Proposal Pattern

```json
{
  "schema": "pointer_gpf.v2.fix_proposal.v1",
  "description": "Remove the early return that prevents feedback state from updating after a hit.",
  "candidate_file": "res://scripts/enemies/test_enemy.gd",
  "edits": [
    {
      "kind": "replace_text",
      "find": "\treturn  # gpf_seeded_bug:hit_feedback_shader_not_updated\n",
      "replace": ""
    }
  ]
}
```

Why this is acceptable:

- file is listed by the fix plan
- edit is small
- `find` is unique
- the change maps directly to failed runtime evidence
- the same repro can verify the fix

## Rejection Examples

Candidate mismatch:

```json
{
  "schema": "pointer_gpf.v2.fix_proposal.v1",
  "candidate_file": "res://scripts/unrelated.gd",
  "edits": [
    {
      "kind": "replace_text",
      "find": "pass",
      "replace": ""
    }
  ]
}
```

Expected reason:

- `candidate_file is not present in plan_bug_fix.candidate_files`

Broad edit:

```json
{
  "schema": "pointer_gpf.v2.fix_proposal.v1",
  "candidate_file": "res://scripts/enemies/test_enemy.gd",
  "edits": [
    {
      "kind": "replace_text",
      "find": "func ",
      "replace": "func "
    }
  ]
}
```

Expected reason during application:

- `find text must appear exactly once`

## Validation

Run:

```powershell
python -m unittest D:\AI\pointer_gpf\v2\tests\test_bug_fix_proposal.py
```

For a real repair, pass the proposal into:

```powershell
python -m v2.mcp_core.server --tool repair_reported_bug --project-root D:\AI\pointer_gpf_testgame --bug-report "<bug>" --expected-behavior "<expected>" --steps-to-trigger "<steps>" --location-node <node> --evidence-plan-file <plan.json> --fix-proposal-file <proposal.json>
```
