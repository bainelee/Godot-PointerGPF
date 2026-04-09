# MCP 核心不变量

## 通用性约束（强制）

- MCP 的能力定义必须是 **Godot 通用能力**，不得绑定任一具体游戏世界观、剧情或专有系统。
- 任何包含具体游戏术语的 flow、步骤 ID、文案，仅可作为 **legacy fixture（兼容样例）**，不得作为默认产品语义。
- 客户端与 CI 的验收依据应聚焦通用契约：工具调用、三阶段播报、产物结构、错误码稳定性。

## 测试收尾规则（强制）

- 任何一次测试流程结束后（无论成功、失败、超时、门禁失败），必须执行收尾关闭动作（`closeProject`）。
- `closeProject` 的语义固定为：**停止 Play 运行态**，并返回编辑器空闲态；默认不关闭 Godot 编辑器进程。
- 关闭动作属于固定执行流程的一部分，不能省略，不能因“本次失败”而跳过。
- 若关闭请求未得到桥接响应，也必须记录“已发起关闭请求”的证据字段，并继续按失败结果返回。

## 引擎启动责任（强制）

- 当用户触发任何基础测试流程或等价验证流程时，若检测到目标引擎未打开，系统必须先自动打开引擎并进入可运行测试态，再继续执行。
- 禁止把“需要用户先打开引擎/先点播放”作为默认执行路径；系统侧必须先尝试自动处理。
- 仅当系统侧自动启动与门控切换均失败时，才允许返回失败；失败返回必须包含已执行动作、当前阻塞点、下一步可直接执行动作。

## 运行桥接挂载规则（强制）

- 运行桥接脚本必须以运行时可见方式挂载（autoload），不得仅依赖编辑器树临时节点。
- 节点解析与交互目标必须限定在当前运行场景（`current_scene`）内，避免误命中编辑器树同名节点。

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
