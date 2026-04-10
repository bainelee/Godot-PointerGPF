# 旧工程 MCP 与 pointer_gpf 对照清单（跑流程 + 自动修）

## 1. 目的

本文件用于对照「旧工程 MCP」与当前 pointer_gpf 仓库在「跑流程 + 自动修」上的差异，便于补齐文档与后续实现决策。

## 2. 旧工程侧（Legacy）

**阻塞**：未设置 `GPF_LEGACY_MCP_ROOT`，无法扫描旧仓库。用户需在本地设置该环境变量（指向旧 MCP 工程根目录）后补充本节；届时可在该根目录下用终端递归查找文件名包含 `mcp`、`flow`、`fix`、`repair`、`bug` 的文件（不区分大小写），例如 PowerShell：

```powershell
$root = $env:GPF_LEGACY_MCP_ROOT
Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match '(?i)mcp|flow|fix|repair|bug' } |
  Select-Object -ExpandProperty FullName
```

## 3. 本仓库当前实现（Current / pointer_gpf）

### 3.1 相关工具（注册与实现）

以下工具在 `mcp/server.py` 中实现并挂入工具分发映射（约 `3769:3772:mcp/server.py` 及 `TOOLS` 元数据块 `3639` 段附近）：

| 工具名 | 职责摘要 |
|--------|----------|
| `run_game_basic_test_flow` | 按给定参数执行基础测试流程（文件桥），失败时在 `details` 中可带 `suggested_next_tool` 等，见 `_tool_run_game_basic_test_flow`（约 `2794` 行起）。 |
| `run_game_basic_test_flow_by_current_state` | 先按当前状态刷新/对齐流程再调用 `run_game_basic_test_flow`，见 `_tool_run_game_basic_test_flow_by_current_state`（约 `2984` 行起）。 |
| `run_basic_test_flow_orchestrated` | 显式 opt-in 下多轮串联「按当前状态跑基础流程」与 `auto_fix_game_bug`，见 `_tool_run_basic_test_flow_orchestrated`（约 `3020` 行起）。 |
| `auto_fix_game_bug` | 独立自动修工具，见 `_tool_auto_fix_game_bug`（约 `3113` 行起）。 |

### 3.2 默认行为：基础流程是否会自动调用 auto_fix？

**不会。** `run_game_basic_test_flow` / `run_game_basic_test_flow_by_current_state` 默认不在失败后自动调用 `auto_fix_game_bug`；失败路径通过 `suggested_next_tool`、`auto_fix_arguments_suggestion` 等供编排层或助手**显式**决定是否调用自动修。

依据：

- `docs/design/99-tools/14-mcp-core-invariants.md`「能力与边界」：**自动修工具非串联默认环节**；基础流程**不会**在失败后自动调用自动修；串联需使用 `run_basic_test_flow_orchestrated` 且 **`orchestration_explicit_opt_in=true`**（同节与编排工具说明）。
- `mcp/server.py` 中 `_tool_run_basic_test_flow_orchestrated`：若 `orchestration_explicit_opt_in` 不为真则直接 `INVALID_ARGUMENT` 拒绝（约 `3022:3030:mcp/server.py`）。

### 3.3 `bug_fix_strategies.py`：`DEFAULT_STRATEGIES` 中 `strategy_id` 顺序

定义于 `mcp/bug_fix_strategies.py` 中 `DEFAULT_STRATEGIES` 元组（约 `273:278:mcp/bug_fix_strategies.py`），按注册顺序为：

1. `signal_disconnected_hint`
2. `scene_button_disabled_false`
3. `scene_mouse_filter_pass`
4. `button_not_clickable`

（未匹配策略时诊断侧可出现 `generic`，见同文件 `default_diagnosis`。）

### 3.4 NL 路由：短语「跑一遍基础测试流程」

`mcp/nl_intent_router.py` 中 `route_nl_intent` 对**完全一致**的输入 `跑一遍基础测试流程` 返回：

- 类型：`IntentRoute`（`dataclass`，字段 `target_tool: str`、`reason: str`，约 `8:11:mcp/nl_intent_router.py`）。
- 取值：`IntentRoute(target_tool="run_game_basic_test_flow_by_current_state", reason="basic_flow_run")`（`_ALIASES` 条目，约 `17:17:mcp/nl_intent_router.py`）。

## 4. 差异表

| 能力项 | 旧工程（待填） | 本仓库当前 | 计划 Task 编号 |
|--------|----------------|------------|----------------|
| 默认是否串联 auto_fix | 待路径 | 否；仅 `run_basic_test_flow_orchestrated` 在 `orchestration_explicit_opt_in=true` 时串联 | `14-mcp-core-invariants.md` 所述编排相关为 Task 5 |
| 策略数量/类型 | 待路径 | `DEFAULT_STRATEGIES` 共 4 条专用策略（上表 `strategy_id`）；另可有 `generic` 诊断 | —（待与父计划对齐） |
| 是否存在 L2 外部修复后端 | 待路径 | 代码库内未检索到以「L2」「外部修复」等命名的专用后端；自动修为仓库内 `auto_fix_game_bug` + `bug_fix_strategies` 路径 | —（待与父计划对齐） |
| NL「跑流程」目标工具名 | 待路径 | 精确短语「跑一遍基础测试流程」→ `run_game_basic_test_flow_by_current_state` | Task 0（本清单） |

## 5. 下一步

- 用户提供并导出 `GPF_LEGACY_MCP_ROOT` 后：补全第 2 节扫描结果，并将第 4 表「旧工程」列改为可验证路径/行为摘要，与「本仓库当前」逐项对照更新。
