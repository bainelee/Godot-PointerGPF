# Gameplay Flow 自动化路线图

## 已具备

- JSON flow 契约与解析（`flow_parser`、`flow_runner`）。
- `run_game_flow` dry-run：CI 可验证 CLI 与产物路径，无需 Godot。
- Stepwise：`start_stepwise_flow` → `prepare_step` / `execute_step` / `verify_step`。
- Fix loop：`resume_fix_loop` 与 `fix_loop_state.json` 回合结构。
- Cursor Chat 插件：`start_cursor_chat_plugin`、`pull_cursor_chat_plugin`。

## 短期

- 扩充 `flows/suites/regression/` 与契约测试，保证迁移后路径解析稳定。
- 文档与 CI 对齐：`.github/workflows/mcp-smoke.yml`、`mcp-integration.yml` 覆盖 legacy 工具关键字与最小 dry-run。

## 中期

- 统一「基础测试流」（`run_game_basic_test_flow`）与 legacy runner 的观测字段，便于单一验收清单。
- 可选：将常用场景固化为 `tools/game-test-runner/scripts/` 下的参数化包装。

## 长期

- 多项目模板与 `gtr.config.json` 约定下沉到采用指南；减少环境变量特例。
