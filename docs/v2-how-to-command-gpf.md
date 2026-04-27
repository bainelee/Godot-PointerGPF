# How To Command GPF V2

This document is for users of the current V2 prototype.

Goal:

- keep the natural-language entry usable
- keep the supported phrasing bounded and testable
- avoid pretending that GPF already supports open-ended free-form routing

The same bounded command set is also exposed in code through:

```powershell
python -m v2.mcp_core.server --tool get_user_request_command_guide --project-root D:\AI\pointer_gpf_testgame
```

That tool is the machine-readable form of this document.

## Core Rule

Use short, explicit, task-shaped requests.

Prefer requests that clearly map to one of these current user goals:

- run the basic test flow
- regenerate the project basicflow
- analyze why the project basicflow is stale
- run project preflight
- configure the Godot executable path
- report a bug for the repair workflow

Do not assume GPF currently supports broad conversational interpretation for unrelated engineering tasks.

## Recommended Request Shapes

### 1. Run The Basic Test Flow

Recommended requests:

- `跑基础测试流程`
- `跑基础流程`
- `执行基础测试流程`
- `run basicflow`
- `run the basic flow`

Current behavior:

- if the saved project `basicflow` is fresh, the upper layer can route toward `run_basic_flow`
- if the saved project `basicflow` is stale, the upper layer can instead route toward regeneration steps first

So "run basicflow" means:

- "take me to the safest current next step for basicflow execution"

It does not mean:

- "always launch play mode immediately no matter what the project state is"

### 2. Regenerate The Project Basicflow

Recommended requests:

- `生成基础测试流程`
- `重新生成基础流程`
- `重建基础流程`
- `刷新基础流程`
- `regenerate basicflow`

Current behavior:

- the upper layer first routes to `get_basic_flow_generation_questions`
- after the 3 answers are collected, the follow-up tool is `generate_basic_flow`

### 3. Analyze Why Basicflow Is Stale

Recommended requests:

- `分析基础流程为什么过期`
- `分析 basicflow`
- `检查基础流程为什么 stale`
- `inspect basicflow drift`
- `why is basicflow stale`

Current behavior:

- the upper layer routes to `analyze_basic_flow_staleness`

### 4. Run Project Preflight

Recommended requests:

- `跑项目预检`
- `运行项目预检`
- `检查项目状态`
- `检查工程状态`
- `preflight project`
- `run preflight`

Current behavior:

- the upper layer routes to `preflight_project`

### 5. Configure The Godot Executable

Recommended requests:

- `配置 godot 路径`
- `设置 godot 路径`
- `configure godot executable`
- `set godot executable`

Best practice:

- include the full `.exe` path in the same request when possible

Example:

- `配置 godot 路径 D:\Tools\Godot\Godot_v4.4.1-stable_win64.exe`

Current behavior:

- if the request contains a concrete `.exe` path, the upper layer can route directly to `configure_godot_executable`
- if the request does not contain a path, the upper layer should ask for that missing input first

### 6. Report A Bug For Repair

Recommended requests:

- `敌人在受击之后不会按照预期闪烁一次红色，帮我自动修复这个 bug`
- `点击开始按钮后没有进入关卡，帮我修复`
- `HUD 进入关卡后没有出现，帮我查并修`
- `repair this bug: after clicking start, the level does not load`

Current behavior:

- the upper layer routes toward `repair_reported_bug`
- `repair_reported_bug` normalizes the bug report, observes project context, and plans the repro path
- if no model evidence plan is available yet, it stops at `status: awaiting_model_evidence_plan`
- the returned `blocking_point` explains why it stopped
- the returned `next_action` tells the model-facing layer to provide `--evidence-plan-json` or `--evidence-plan-file`
- the returned `model_evidence_plan_instruction` gives the model the expected schema, allowed actions, candidate project facts, and a compact example
- after a reproduced bug and fix planning, if no bounded fix proposal is available yet, it stops at `status: bug_reproduced_awaiting_fix_proposal`
- the returned `next_action` tells the model-facing layer to provide `--fix-proposal-json` or `--fix-proposal-file`
- the returned `model_fix_proposal_instruction` gives the model the expected schema, candidate files, fix goals, acceptance checks, runtime evidence summary, and a compact edit example

Model-facing contracts:

- [v2-model-evidence-plan-contract.md](/D:/AI/pointer_gpf/docs/v2-model-evidence-plan-contract.md)
- [v2-model-fix-proposal-contract.md](/D:/AI/pointer_gpf/docs/v2-model-fix-proposal-contract.md)

Example files:

- `v2/examples/*_evidence_plan.json`
- `v2/examples/*fix_proposal*.json`

Important boundary:

- the deterministic MCP layer does not guess arbitrary runtime evidence or arbitrary code edits by itself
- the language model should choose evidence targets and propose bounded edits
- GPF validates, runs, applies, reruns, and runs regression

Expected final behavior when the model provides the required inputs:

- real `play_mode` repro
- persisted evidence artifacts
- bounded edit applied only inside candidate files
- rerun of the same bug-focused flow
- regression before reporting `fixed_and_verified`
- `artifact_summary`, `repair_summary`, and `user_report` in the result after repro has run

## Current Product Boundary

V2 currently supports:

- a bounded set of explicit high-frequency phrases
- project-aware interpretation for `basicflow`
- bug repair requests through `repair_reported_bug`, with explicit stops when model input is still required
- a thin top-level planner and handler for selected domains

V2 does not currently promise:

- open-domain free-form command understanding
- arbitrary paraphrase support
- automatic execution of every routed tool
- silent play-mode execution from every natural-language request
- arbitrary code edits without a bounded fix proposal

This boundary is intentional.

## Recommended User Habit

Use one short request for one concrete action.

Good:

- `跑项目预检`
- `run basicflow`
- `inspect basicflow drift`
- `配置 godot 路径 D:\Tools\Godot\Godot_v4.4.1-stable_win64.exe`

Avoid:

- `帮我随便看看这个项目现在能不能跑然后如果有问题就帮我修一下再测一遍`
- `做你觉得最合适的 basicflow 操作`
- `顺便把 stale、预检、启动和截图都处理一下`

Those requests are too broad for the current bounded V2 command layer.

## Why This Boundary Exists

The current V2 goal is:

- predictable routing
- explicit behavior
- testable user-facing entrypoints

not:

- "guess everything the user might mean"

When new high-level request shapes are added, they should be added in this order:

1. document the supported user-facing phrasing
2. add or update tests
3. update the planner / handler implementation

That keeps the user contract and the code contract aligned.
