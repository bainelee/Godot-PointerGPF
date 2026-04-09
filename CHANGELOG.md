# Changelog

## Unreleased

- 暂无更新。

## v0.2.4.6 - 2026-04-09

- 发布链路完成“版本单一来源 + tag 驱动 CI”改造：`VERSION` 作为 SSOT，新增 `scripts/sync-version.ps1` 与 `scripts/release.ps1`，并补齐中英文文档与维护者操作说明。
- 强化发布安全防护：发布脚本新增预暂存检查、tag 可用性检查（本地/远端）、`git push --atomic` 推送，降低混入无关改动与半成功发布风险。
- 修复 `release-package.yml` 的 Windows 打包稳定性：改为复制阶段排除 `.godot`，并正确处理 `robocopy` 返回码，避免 tag 触发发布任务误失败。

## v0.2.4.3 - 2026-04-09

- 修复 `install/update-mcp.ps1`：`-ForceRemote` 现在始终优先于本地 `artifact.url` 分支，确保“强制远端更新”语义正确。
- 更新同步范围扩展为 `mcp/`、`gtr.config.json`、`godot_plugin_template/`（支持 `-NoRootSync`），并新增安装后真实版本日志与版本一致性校验（支持 `-FailOnVersionMismatch`）。
- 增强 Windows 解压容错：`Expand-Archive` 失败后自动降级为选择性解压关键目录，规避旧包中深层缓存路径导致的中断。
- 发布流程改为 staging 打包并排除 `examples/**/.godot/**` 缓存目录；补充 update 冒烟测试与文档说明。

## v0.2.4.2 - 2026-04-09

- 修复 Godot 插件模板 `addons/pointer_gpf/plugin.cfg` 的 `script` 路径：由绝对路径 `res://addons/pointer_gpf/plugin.gd` 改为相对路径 `plugin.gd`，避免 Godot 在部分加载链路中拼接出错误路径导致插件无法加载。
- 同步更新版本元数据与文档版本号，发布补丁包供 `update-mcp.ps1` 远端更新通道使用。

## v0.2.4.1 - 2026-04-09

- 支持四段版本号发布策略（`major.minor.patch.build`），用于小更新快速迭代。
- 新增命令式更新入口：`pointer-gpf.cmd` 与 `install/pointer-gpf.ps1`，用户可直接运行 `.\pointer-gpf.cmd update`。
- 重构中英文首页 README，增加双语导航、封面图、清晰的 Agent/人工分工说明。
- 发布流程新增双语 release notes 模板，统一发版说明口径。

## v0.2.4 - 2026-04-09

- 修复 MCP stdio 传输兼容性：服务端可自动识别 `Content-Length` 与 JSON 行输入，并按同协议回包，避免客户端握手后超时/Aborted。
- 新增传输兼容回归测试 `tests/test_mcp_transport_protocol.py`，覆盖两类 initialize 往返。
- 清理跨项目联调阶段的临时调试流程文档，保持发行包内容精简。

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
