# MCP 差异审计（2026-04-10）

## 输入来源

- 旧仓库（old repo）：`D:/GODOT_Test/old-archives-sp`
- 旧提交（old commit）：`522744d`
- 新仓库（new repo）：`D:/AI/pointer_gpf`
- 机器可读产物：`docs/mcp-gap-analysis-2026-04-10.json`（由 `scripts/mcp_gap_audit.py` 生成）

## 结论摘要

- **旧版 MCP 工具面（`TOOL_TO_METHOD` 键）数量**：21  
- **当前 `mcp/server.py` 中 `_build_tool_map` 工具数量**：18  
- **相对旧版缺失的工具名（`missing_tools`）数量**：20（两版均保留 `get_mcp_runtime_info`）  
- **约定前缀下、旧仓库存在但当前仓库缺失的路径条数合计**：106（按前缀拆分见下表）

| 前缀 | 缺失路径数 |
| --- | ---: |
| `tools/game-test-runner/core/` | 16 |
| `tools/game-test-runner/mcp/` | 18 |
| `tools/game-test-runner/scripts/` | 10 |
| `tools/game-test-runner/config/` | 3 |
| `flows/` | 22 |
| `addons/test_orchestrator/` | 11 |
| `docs/design/99-tools/` | 9 |
| `docs/testing/` | 17 |

## 修复输入清单（来自 JSON）

- **缺失工具（`missing_tools`）**：`cancel_test_run`、`check_test_runner_environment`、`execute_step`、`get_flow_timeline`、`get_live_flow_progress`、`get_test_artifacts`、`get_test_report`、`get_test_run_status`、`list_test_scenarios`、`prepare_step`、`pull_cursor_chat_plugin`、`resume_fix_loop`、`run_and_stream_flow`、`run_game_flow`、`run_game_test`、`run_stepwise_autopilot`、`start_cursor_chat_plugin`、`start_game_flow_live`、`start_stepwise_flow`、`step_once`、`verify_step`  
- **路径样例（`missing_path_samples`）**：见 JSON 中各前缀下最多 10 条示例路径  

## 重新生成命令

```powershell
python scripts/mcp_gap_audit.py `
  --old-repo "D:/GODOT_Test/old-archives-sp" `
  --old-commit "522744d" `
  --new-repo "D:/AI/pointer_gpf" `
  --out "docs/mcp-gap-analysis-2026-04-10.json"
```
