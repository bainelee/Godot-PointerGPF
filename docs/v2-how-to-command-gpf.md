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

## Current Product Boundary

V2 currently supports:

- a bounded set of explicit high-frequency phrases
- project-aware interpretation for `basicflow`
- a thin top-level planner and handler for selected domains

V2 does not currently promise:

- open-domain free-form command understanding
- arbitrary paraphrase support
- automatic execution of every routed tool
- silent play-mode execution from every natural-language request

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
