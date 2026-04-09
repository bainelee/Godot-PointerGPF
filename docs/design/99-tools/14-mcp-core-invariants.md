# MCP 核心不变量

## 通用性约束（强制）

- MCP 的能力定义必须是 **Godot 通用能力**，不得绑定任一具体游戏世界观、剧情或专有系统。
- 任何包含具体游戏术语的 flow、步骤 ID、文案，仅可作为 **legacy fixture（兼容样例）**，不得作为默认产品语义。
- 客户端与 CI 的验收依据应聚焦通用契约：工具调用、三阶段播报、产物结构、错误码稳定性。

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
