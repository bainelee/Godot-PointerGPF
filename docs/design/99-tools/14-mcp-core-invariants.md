# MCP 核心不变量

## 通用性约束（强制）

- MCP 的能力定义必须是 **Godot 通用能力**，不得绑定任一具体游戏世界观、剧情或专有系统。
- 任何包含具体游戏术语的 flow、步骤 ID、文案，仅可作为 **legacy fixture（兼容样例）**，不得作为默认产品语义。
- 客户端与 CI 的验收依据应聚焦通用契约：工具调用、三阶段播报、产物结构、错误码稳定性。

## 测试收尾规则（强制）

- 任何一次测试流程结束后（无论成功、失败、超时、门禁失败），必须执行收尾关闭动作（`closeProject`）。
- `closeProject` 的语义固定为：**停止 Play 运行态**，并返回编辑器空闲态；默认不关闭 Godot 编辑器进程。
- 收尾若未能在桥接层完成（例如无法写入 `pointer_gpf/tmp/auto_stop_play_mode.flag`），适配器必须返回 **`ok=false` 与稳定错误码**（契约中为 `STOP_FLAG_WRITE_FAILED`），不得冒充成功；细节见 `mcp/adapter_contract_v1.json`（`runtime_bridge` / `error_codes`）与 `docs/mcp-real-runtime-input-contract-design.md` §8。
- 关闭动作属于固定执行流程的一部分，不能省略，不能因“本次失败”而跳过。
- 若关闭请求未得到桥接响应，也必须记录“已发起关闭请求”的证据字段，并继续按失败结果返回。

## 引擎启动责任（强制）

- 当用户触发任何基础测试流程或等价验证流程时，若检测到目标引擎未打开，系统必须先自动打开引擎并进入可运行测试态，再继续执行。
- 禁止把“需要用户先打开引擎/先点播放”作为默认执行路径；系统侧必须先尝试自动处理。
- 仅当系统侧自动启动与门控切换均失败时，才允许返回失败；失败返回必须包含已执行动作、当前阻塞点、下一步可直接执行动作。

## 运行桥接挂载规则（强制）

- 运行桥接脚本必须以运行时可见方式挂载（autoload），不得仅依赖编辑器树临时节点。
- 节点解析与交互目标必须限定在当前运行场景（`current_scene`）内，避免误命中编辑器树同名节点。

## 运行态诊断观测（强制）

- 在等待 `pointer_gpf/tmp/response.json` 时，MCP **必须**能够并行读取 `pointer_gpf/tmp/runtime_diagnostics.json`（见 `adapter_contract_v1.json` → `runtime_diagnostics` 与 `16-pointer-gpf-runtime-diagnostics-bridge.md`）。
- 当诊断快照的 `severity` 为 `error` 或 `fatal` 时，基础流程执行应**尽快失败**并返回可验证证据（含 `runtime_diagnostics` 与 `ENGINE_RUNTIME_STALLED` 或等价错误码），不得长时间空等到 `step_timeout`。
- 外部工具（含编辑器侧 Godot 工具链）可将诊断写入同一 schema，以便与 PointerGPF 文件桥对齐。

## 能力与边界（文档化，避免与产品想象混淆）

以下条目用于对齐「文档/口头预期」与「当前实现」，**不改变**上文强制条目的验收口径。

- **不强制结束操作系统进程**：默认实现通过文件桥请求停止 Play，**不保证**在卡死或桥接无响应时结束 Godot 可执行文件进程；需要硬终止时须由显式策略或人工处理（见 `docs/superpowers/plans/2026-04-10-mcp-game-freeze-vs-expected-autonomous-loop.md` 第二部分原因 C、第四部分 Task 3）。
- **诊断文件不等于编辑器输出里的全部信息**：`runtime_diagnostics.json` 聚合桥接失败与（在支持的引擎版本下）通过 `OS.add_logger` 转发的引擎 `_log_error` 等来源，**仍可能**漏掉未进入该通道的日志或仅阻塞主线程、无法刷新磁盘的故障；不得把它等同于「人类在 Godot 输出窗口看到的每一句话」。
- **默认串联自动修（可关闭）**：`run_game_basic_test_flow` 与 `run_game_basic_test_flow_by_current_state` 默认在流程未通过时，在 **`max_repair_rounds`**（1–8，默认 2）与 **`auto_fix_max_cycles`**（默认 3，0 表示跳过 `auto_fix` 调用）上限内交替执行 **`auto_fix_game_bug`** 与再次验证。传 **`auto_repair: false`** 或设置环境变量 **`GPF_AUTO_REPAIR_DEFAULT=0`** 可恢复「仅跑流程、不自动修」。以下错误码**不**进入修复环，仍直接抛 `AppError`：`INVALID_ARGUMENT`、`TEMP_PROJECT_FORBIDDEN`、`INVALID_GODOT_PROJECT`、`BROADCAST_ENTRY_REQUIRED`、`FLOW_GENERATION_BLOCKED`。
- **单工具 `auto_fix_game_bug`**：仍可作为独立工具调用；其内部验证跑流程时强制 **`auto_repair: false`**，避免递归。`STEP_FAILED`、`ENGINE_RUNTIME_STALLED`、`TIMEOUT` 等失败路径的错误详情中仍可携带 `suggested_next_tool` / `auto_fix_arguments_suggestion`，供客户端展示或手工续调。
- **失败后的 `hard_teardown` 证据**：流程失败且已尝试 `closeProject` 时，错误 `details` 须包含 **`hard_teardown`**：`user_must_check_engine_process` 在「已请求关闭但未收到应答」时为真；**默认不**终止操作系统内的 Godot 进程。仅当调用方显式传入 **`force_terminate_godot_on_flow_failure=true`** 时，才在「关闭未确认」条件下尝试按命令行匹配 `project_root` 并结束进程（**可能关掉正在编辑该工程的编辑器**），详见同目录计划文档 Task 3。
- **编排工具（兼容别名）**：**`run_basic_test_flow_orchestrated`** 仍要求 **`orchestration_explicit_opt_in=true`**；实现上等价于 **`run_game_basic_test_flow_by_current_state`** 且 **`auto_repair=true`**，并将 **`max_orchestration_rounds`** 映射为 **`max_repair_rounds`**。新集成应优先直接调用 `run_game_basic_test_flow_by_current_state`。

## 临时项目安全规则（强制）

- 默认禁止把系统临时目录项目作为真实测试目标工程。
- 对临时目录仅允许在测试代码中显式放行（如 `allow_temp_project=true`）；默认路径不得自动拉起引擎。
- 当命中此限制时必须返回结构化错误（包含阻塞点与下一步动作），不得继续执行步骤。

## 协议

- stdio：**Content-Length** 定界 JSON-RPC；`initialize` 后 `tools/list` / `tools/call`。
- CLI：`python mcp/server.py --tool <name> --args '<json>'`；成功 stdout 为 `{"ok":true,"result":...}`，业务错误为 `{"ok":false,"error":{"code","message",...}}` 且进程退出码非零。

## 工具分类

- **项目/插件**：`install_godot_plugin` 等，操作目标 `project_root`。
- **画像与 seed**：`init_project_context`、`generate_flow_seed`。
- **基础可执行流**：`design_game_basic_test_flow`、`run_game_basic_test_flow`（文件桥）。
- **Legacy gameplayflow**：列表见根 `mcp/server.py` 中 `_LEGACY_GAMEPLAYFLOW_TOOL_NAMES`；实现委托 `tools/game-test-runner/mcp`。

## 播报门禁

- 对 `BROADCAST_REQUIRED_TOOLS`：默认拒绝并返回 `BROADCAST_ENTRY_REQUIRED`，引导使用 `start_cursor_chat_plugin`。
-  bypass：`allow_non_broadcast: true` + `MCP_ALLOW_NON_BROADCAST=1`。

## 错误码稳定

- 集成测试依赖稳定 `code`（如 `NOT_FOUND`、`INVALID_ARGUMENT`、`BROADCAST_ENTRY_REQUIRED`）；客户端应依赖 `code` 而非文案。

## CI

- `mcp-smoke` / `mcp-integration` 须保留对 **`run_game_flow`**、**`start_stepwise_flow`**、**`pull_cursor_chat_plugin`** 的引用（见 `tests/test_ci_legacy_coverage.py`）。
