# Changelog

## v0.2.1 - 2026-04-06

- 完成 MCP `stdio` 入口与 CLI 入口治理，统一工具路由与输出布局。
- 新增产物契约校验脚本 `scripts/assert-mcp-artifacts.ps1`，并接入 smoke/integration 工作流。
- 新增 `.github/workflows/mcp-integration.yml`，输出 `mcp_integration_trend_report.json` 趋势报告产物。
- 补齐发布元数据维护流程，新增 `scripts/update-version-manifest.ps1` 并完善文档（`docs/quickstart.md`、`docs/mcp-testing-spec.md` 等）。

## v0.2.0 - 2026-04-03

- 首次发布：插件安装与启用、项目上下文初始化/刷新、flow seed 生成、Adapter Contract v1。
