# Changelog

## v0.2.3 - 2026-04-09

- 修复 `install/start-mcp.ps1` 生成的 Cursor MCP 配置，默认输出解析后的 Python 可执行路径并显式加入 `-u` 与 `--stdio`，降低连接超时与 `Aborted` 风险。
- 更新 `README.md` 与 `docs/quickstart.md` 的 MCP 配置示例，统一为更稳健的 stdio 启动参数。
- 新增回归测试 `tests/test_start_mcp_config.py`，防止启动配置回退到易超时形态。

## v0.2.2 - 2026-04-09

- 新增 Figma 协同 UI 对比工具链：`figma_design_to_baseline`、`compare_figma_game_ui`、`annotate_ui_mismatch`、`approve_ui_fix_plan`、`suggest_ui_fix_patch`。
- 新增修复授权门禁：未授权不能生成修复建议。
- 扩展 CI smoke/integration，覆盖 Figma 协同最小闭环。
- 扩展产物校验脚本 `scripts/assert-mcp-artifacts.ps1`，支持 `-ValidateFigmaPipeline`。
- 更新适配器契约与文档，补充 `check.kind=visual_hard` 证据字段约定。

## v0.2.1 - 2026-04-06

- 完成 MCP `stdio` 入口与 CLI 入口治理，统一工具路由与输出布局。
- 新增产物契约校验脚本 `scripts/assert-mcp-artifacts.ps1`，并接入 smoke/integration 工作流。
- 新增 `.github/workflows/mcp-integration.yml`，输出 `mcp_integration_trend_report.json` 趋势报告产物。
- 补齐发布元数据维护流程，新增 `scripts/update-version-manifest.ps1` 并完善文档（`docs/quickstart.md`、`docs/mcp-testing-spec.md` 等）。

## v0.2.0 - 2026-04-03

- 首次发布：插件安装与启用、项目上下文初始化/刷新、flow seed 生成、Adapter Contract v1。
