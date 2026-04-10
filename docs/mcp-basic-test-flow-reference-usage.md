# 基础测试流程参照：使用方式与自然语言触发

本文档供 **MCP 客户端、自动化代理与终端用户** 使用：说明如何读取「流程预期 / 游戏类型参照」类材料，以及可通过哪些**自然语言**让 `route_nl_intent` 路由到对应工具。

## 1. MCP 工具（推荐入口）

| 动作 | 工具名 | 说明 |
|------|--------|------|
| 一次性取出本说明全文 + 目标工程内路径提示 | `get_basic_test_flow_reference_guide` | 可选传入 `project_root`，返回 `markdown` 与 `project_context_paths` |
| 仅判断「这句话该调用哪个工具」 | `route_nl_intent` | 传入 `text`，返回 `target_tool`、`reason`，以及本仓库示例工程路径字段 `canonical_example_project_root` / `canonical_example_project_rel`（见 **`docs/gpf-nl-basic-flow-clarifying-questions.md`**） |

代理执行顺序建议：用户口述需求 → `route_nl_intent` → 若 `target_tool` 为跑流程类工具，先按 **`docs/gpf-nl-basic-flow-clarifying-questions.md`** 做用户澄清（AskQuestion）→ 再 `tools/call` 执行之。

## 2. 自然语言示例 → `route_nl_intent` 结果

以下为常见说法（**不必一字不差**；未列出的变体可能仍被模糊规则命中，也可能返回 `unknown`）。

| 用户说法（示例） | `target_tool`（意图） |
|------------------|----------------------|
| 基础测试流程怎么用 | `get_basic_test_flow_reference_guide` |
| 如何使用基础测试流程类型参照 | `get_basic_test_flow_reference_guide` |
| 基础测试流程使用说明 | `get_basic_test_flow_reference_guide` |
| 流程预期说明文档在哪 | `get_basic_test_flow_reference_guide` |
| 游戏类型流程预期查看说明 | `get_basic_test_flow_reference_guide` |
| 设计一个基础测试流程 | `design_game_basic_test_flow` |
| 跑一遍基础测试流程 | `run_game_basic_test_flow_by_current_state` |

**注意**：若同一句中同时出现「设计/生成/创建」或「跑/执行/运行」等动词，路由会优先指向**设计**或**执行**，而不是本说明工具。

## 3. 文档在磁盘上的位置

### PointerGPF 仓库（完整说明）

- 本文件：`docs/mcp-basic-test-flow-reference-usage.md`
- 按游戏类型的流程预期（长文）：`docs/mcp-basic-test-flow-game-type-expectations.md`
- 文档索引：`docs/mcp-docs-index.md`

### 目标 Godot 工程（初始化后）

在目标工程执行 `init_project_context` 或 `refresh_project_context` 后（默认输出于 `pointer_gpf/project_context/`）：

- 流程编写指南（含精简「按游戏类型」速查）：`04-flow-authoring-guide.md`
- 运行阶段与静态可点性等：`06-operational-profile.md`
- 候选动作/断言：`05-flow-candidate-catalog.md` 与 `index.json`

## 4. 典型工作流（快速）

1. 在目标工程执行 `init_project_context`（或 `refresh_project_context`）。
2. 阅读 `04-flow-authoring-guide.md` 与 `06-operational-profile.md`（或由 `get_basic_test_flow_reference_guide` 返回的路径字段）。
3. 调用 `design_game_basic_test_flow` 生成流程；需要更深类型对照时打开仓库内 `docs/mcp-basic-test-flow-game-type-expectations.md`。
4. 使用 `run_game_basic_test_flow` 或 `run_game_basic_test_flow_by_current_state` 执行（须满足运行态与文件桥等前置条件，见适配契约与不变量文档）。执行时默认会轮询 `pointer_gpf/tmp/runtime_diagnostics.json`；可用参数 `observe_engine_errors: false` 关闭（仅建议用于回归/调试）。
5. **默认自动修复闭环**：上述两个 run 工具默认 **`auto_repair: true`**（可用 **`auto_repair: false`** 或环境变量 **`GPF_AUTO_REPAIR_DEFAULT=0`** 关闭）。成功或结束后，结果中可能含 **`auto_repair`** 字段（`final_status`、`rounds` 等）。仍可直接调用 **`auto_fix_game_bug`** 做独立诊断修复。**AI 代理 / IDE 会话**：若环境中有 **`GPF_AUTO_REPAIR_DEFAULT=0`** 但仍希望默认开启自动修复，请使用 **`GPF_AGENT_SESSION_DEFAULTS=1`** 或 JSON **`agent_session_defaults: true`**（不得由 CI 设置）；见 **`docs/gpf-ai-agent-integration.md`**。
6. 若返回 `ENGINE_RUNTIME_STALLED`，查看同目录 `runtime_diagnostics.json` 与错误体中的 `auto_fix_arguments_suggestion`；在 **`auto_repair: false`** 模式下可手工接续调用 `auto_fix_game_bug`。
7. 失败时查看错误 `details.hard_teardown`：`user_must_check_engine_process` 为真表示 Play 可能仍在运行。仅在可接受**结束 Godot 进程**（可能关闭编辑器）时，对 `run_game_basic_test_flow` / `run_game_basic_test_flow_by_current_state` 传入 **`force_terminate_godot_on_flow_failure: true`**。
8. **兼容工具 `run_basic_test_flow_orchestrated`**：仍须 **`orchestration_explicit_opt_in: true`**；行为等价于 `run_game_basic_test_flow_by_current_state` 且开启自动修复，**`max_orchestration_rounds`** 对应 **`max_repair_rounds`**。新集成请直接调用 `run_game_basic_test_flow_by_current_state` 并传 **`max_repair_rounds` / `auto_fix_max_cycles`**。
9. **L2 外部修复（可选）**：若设置环境变量 **`GPF_REPAIR_BACKEND_CMD`**（可含 `{payload_file}`、`{project_root}`），`auto_fix_game_bug` 内在 L1 策略未打上补丁时会尝试该命令；命令须在 stdout **最后一行非空行**输出 JSON：`{"applied": true/false, "changed_files": [], "notes": ""}`。

### 4.1 用户旅程与自动排障说明（推荐阅读）

- 面向最终用户的四步旅程、**`remediation_matrix` 与 `auto_repair` 的精确含义**、返回字段导读：见 **`docs/gpf-user-journey-auto-remediation.md`**。
- 机器可读的修复类别与上限表：仓库 **`mcp/adapter_contract_v1.json`** 根字段 **`remediation_matrix`**（亦可通过 MCP 工具 **`get_adapter_contract`** 获取整份契约）。

## 5. 维护说明

- 新增或调整自然语言触发时，应同步修改 `mcp/nl_intent_router.py` 与本文件表格，并更新 `tests/test_nl_intent_router_expanded.py`。
