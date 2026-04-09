# Godot MCP Gameplay Flow 架构（legacy + 根 MCP 桥接）

## 设计前提

- 本架构面向 **全类型 Godot 项目**，不绑定单一游戏。
- `tools/game-test-runner` 中可能存在 legacy fixture（历史流程资产），其作用是兼容历史回放，不代表默认产品能力模型。

## 分层

1. **根 MCP**（`mcp/server.py`）：面向 Cursor 等客户端的统一入口；除 Figma/画像/基础测试流外，通过桥接表暴露 **legacy gameplayflow** 工具名（与 `tools/game-test-runner/mcp` 一致）。
2. **game-test-runner MCP**（`tools/game-test-runner/mcp/server.py`）：实现 `run_game_flow`、`start_stepwise_flow`、`pull_cursor_chat_plugin` 等；含 **播报门禁**（`BROADCAST_ENTRY_REQUIRED`）与 **Chat Relay** 会话策略。
3. **Runner / Driver**（`tools/game-test-runner/core/`）：解析 `flows/**/*.json`，驱动 Godot 测试进程与 `test_driver` IPC。

## 数据面

- Flow 资产：仓库 `flows/`（可用 `flows/migration_map.json` 做别名）。
- 单次运行产物：`artifacts/test-runs/<run_id>/`（`report.json`、`flow_report.json`、`step_timeline.json` 等）。
- 项目内桥：`pointer_gpf/tmp/command.json` ↔ `response.json`（基础测试流）；stepwise / chat 另见各 handler 状态文件。

## 播报与非播报

- 默认：`run_game_flow`、`start_stepwise_flow` 等需经 **`start_cursor_chat_plugin`** 主路径，或显式 `allow_non_broadcast: true` 且环境 **`MCP_ALLOW_NON_BROADCAST=1`**（供自有脚本/CI）。
- Chat 拉取：**`pull_cursor_chat_plugin`** 按 `run_id` 消费插件侧队列事件。

## 脚本入口

见 `tools/game-test-runner/scripts/`（`run_gameplay_stepwise_chat.py`、`run_gameplay_regression.ps1`、`run_smoke_continue_chat_broadcast.ps1`）。
