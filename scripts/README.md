# Scripts Index

本文件用于统一维护 `scripts/` 的用途、输入输出与对应文档，避免脚本与文档说明分散。

## 使用约定

- 默认在仓库根目录执行脚本命令。
- PowerShell 脚本建议使用：`powershell -ExecutionPolicy Bypass -File "<script>" ...`
- Python 脚本建议使用：`python "<script>" ...`

## 脚本映射表

| 脚本 | 作用 | 主要输入 | 主要输出 | 对应文档 |
| --- | --- | --- | --- | --- |
| `scripts/assert-mcp-artifacts.ps1` | 校验 MCP 运行产物契约（含可选 Figma/执行层校验） | `ProjectRoot`, `FlowId` | 校验结果（命令退出码与错误信息） | `docs/mcp-testing-spec.md`, `docs/quickstart.md` |
| `scripts/verify-v2-regression.py` | 统一执行 V2 固定回归：单测、预检查、交互 flow、basicflow 问题契约、session 生成链、默认 basicflow 运行、stale 分析、stale override、运行保护验证 | `--project-root` | JSON 结果（`ok` + 各回归项详情） | `docs/v2-status.md`, `docs/v2-handoff.md` |
| `scripts/verify-v2-runtime-guards.py` | 验证 V2 的运行态保护：同工程并发拒绝、多开编辑器拒绝；Windows 下以隐藏辅助窗口方式启动验证进程 | `--project-root`，可选 `--check conflict|multi-editor|all` | JSON 结果（`ok` + 每项保护验证详情） | `docs/v2-status.md`, `docs/v2-handoff.md` |
| `scripts/verify-cross-project.ps1` | 执行示例项目 + 目标项目的跨项目矩阵验证 | `TargetProjectRoot`（必填），可选 `ExampleProjectRoot` | 验证日志与调用结果 | `docs/quickstart.md`, `docs/adoption-overview.md` |
| `scripts/migrate-legacy-layout.ps1` | 将旧布局 `gameplayflow/*` / `gpf-exp` 迁移到 `pointer_gpf/*` | `ProjectRoot`，可选 `DryRun`, `Overwrite` | `pointer_gpf/reports/legacy_layout_migration_report.json` | `docs/migration-checklist.md`, `docs/quickstart.md` |
| `scripts/update-version-manifest.ps1` | 回填/更新 `mcp/version_manifest.json` 的稳定通道信息 | `Version`, `ArtifactUrl`, `Sha256` | 更新后的 `mcp/version_manifest.json` | `docs/quickstart.md` |
| `scripts/generate_requirements_index.py` | 生成权威需求索引 JSON | `docs/authoritative-requirements/*.md` | `docs/authoritative-requirements/requirements-index.json` | `docs/authoritative-requirements/README.md` |
| `scripts/mcp_gap_audit.py` | 对比旧归档与当前仓库的 MCP 工具面与路径缺口 | `--old-repo`, `--old-commit`, `--new-repo`, `--out` | gap JSON 报告 | `docs/mcp-gap-analysis-2026-04-10.md` |
| `scripts/verify-release-package-layout.py` | 校验 release zip 是否符合 `pointer_gpf/` 单目录载荷约束 | `zip_path` | JSON 结果（`ok`/`missing`） | `docs/quickstart.md`, `docs/design/99-tools/15-mcp-full-audit-critical-task-2026-04-10.md` |
| `scripts/verify-release-manifest-artifact.py` | 下载并校验 manifest 指向的 stable release 资产（布局 + 工具面） | 可选 `manifest_path` | JSON 结果（含 sha、布局、工具面检查） | `docs/design/99-tools/15-mcp-full-audit-critical-task-2026-04-10.md`, `docs/mcp-implementation-status.md` |

## 维护规则

- 新增脚本时，必须在本表追加一行，并补齐至少一个对应文档链接。
- 修改脚本输入输出后，需同步更新本表与对应文档。
- 若脚本面向 CI 使用，建议在对应工作流注释中引用本文件路径。

