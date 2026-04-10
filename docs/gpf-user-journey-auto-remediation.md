# 用户旅程：安装 GPF → 初始化 → 设计流程 → 自然语言跑流程（与自动排障）

本文面向**最终用户**与集成方，说明在自有 Godot 工程中使用 PointerGPF（GPF）时的典型路径、默认会自动尝试哪些动作、如何阅读一次跑流程的返回，以及如何关闭自动修复或接入可选的外部修复命令。**不涉及**任何特定品牌编辑器。

## 1. 四步旅程与常见失败点

| 步骤 | 你在做什么 | 常见失败点（示例） |
|------|------------|-------------------|
| 安装 GPF | 将插件拷入 `addons/`，在 `project.godot` 启用插件 | 插件未启用、路径错误 |
| 初始化上下文 | 调用 `init_project_context` / `refresh_project_context` | 扫描范围过大、权限或路径问题 |
| 设计基础测试流程 | 调用 `design_game_basic_test_flow` 等 | 缺少可执行证据导致生成被阻塞 |
| 自然语言跑流程 | 经 `route_nl_intent` 或直接调用 `run_game_basic_test_flow_by_current_state` | 未进入 `play_mode`、步骤超时、脚本/场景错误 |

上述「自动排障」**仅在** MCP 工具实际执行跑流程且满足运行门禁（真实 `play_mode` 等）的前提下才会触发；不会把「未运行」冒充为「已通过」。

## 2. 「全自动」在 GPF 里的含义

- **会自动尝试的动作集合**由仓库内 `mcp/adapter_contract_v1.json` 的 **`remediation_matrix`** 描述（机器可读）：每一行对应一个 **`remediation_class`**，并标明主要由 **`handler`（确定性动作）**、**`strategy`（工程内补丁/提示）**、**`l2_or_none`（外部命令）** 或 **`none`（仅给证据）** 处理，以及 **`max_auto_attempts`** 建议上限。
- **`auto_repair`** 外层轮次（`max_repair_rounds`）与 **`auto_fix_game_bug`** 内层轮次（`auto_fix_max_cycles`）共同约束总尝试次数；达到上限后结果中会标明 **`exhausted_rounds`** 等状态，**不会**在无证据时返回成功。
- **不是**「任意未预见 bug 必秒修」：未纳入矩阵或标记为 `handled_by: none` 的类别，系统仍应完成「验证 → 定位 → 修复尝试 → 复测」并输出证据，但若无法修复须返回**明确失败态**。

## 3. 如何阅读一次跑流程的返回

- **`tool_usability` / `gameplay_runnability`**：R-002 双目标结论（工具是否可用、游戏流程是否跑通）。
- **`auto_repair`**（若开启）：含 `final_status`、`rounds`；每轮可能含 **`remediation_class`**、**`remediation_handler`**（handler 是否已处理）、**`auto_fix`**（内层修复结果）；汇总 **`remediation_traces`** 为各轮 `auto_fix_game_bug` 的 **`remediation_trace`** 列表。
- **`remediation_trace`**（在 `auto_fix_game_bug` 或上述汇总中）：事件类型为 **`verify` / `locate` / `patch` / `retest`**（及可选 **`bootstrap`**），用于对照 R-001 四阶段记录。

更完整的工具参数与 NL 触发见 **`docs/mcp-basic-test-flow-reference-usage.md`**。

## 4. 配置 `GPF_REPAIR_BACKEND_CMD`（可选 L2）

在环境中设置 **`GPF_REPAIR_BACKEND_CMD`**，命令字符串可使用占位符 **`{payload_file}`**、**`{project_root}`**。命令须在 stdout **最后一行非空行**输出 JSON，例如：

`{"applied": false, "changed_files": [], "notes": "reason"}`

详见 **`docs/mcp-basic-test-flow-reference-usage.md`** 第 4 节附近说明。

## 5. 关闭自动修复

- 调用 run 系列工具时传入 **`"auto_repair": false`**；或  
- 设置环境变量 **`GPF_AUTO_REPAIR_DEFAULT=0`**（脚本/CI 常用）。

关闭后仍会执行真实跑流程，但不会自动串联 **`auto_fix_game_bug`**。
