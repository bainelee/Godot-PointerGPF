# PointerGPF 目录职责与边界说明（基线）

本文档用于统一项目目录语义，降低“同名不同义”导致的维护风险。除非特别说明，以下路径均相对于仓库根目录。

## 一、术语定义（必须区分）

- `仓库根目录`：`D:/AI/pointer_gpf`，用于存放源码与文档。
- `目标项目工作区目录`：目标 Godot 项目中的 `pointer_gpf/`，用于运行时产物（如 `project_context`、`generated_flows`、`gpf-exp`）。
- `release 包根目录`：发布压缩包内的 `pointer_gpf/` 单目录载荷，用于安装和分发。

同名 `pointer_gpf` 在以上三种场景含义不同，文档和脚本必须显式标注语境。

## 二、顶层目录职责（权威映射）

- `mcp/`：主 MCP 服务入口与运行时契约，默认启动入口是 `mcp/server.py`。
- `install/`：安装、更新、启动入口脚本（面向用户和维护者）。
- `tools/game-test-runner/`：游戏测试运行能力与 legacy MCP 子服务实现。
- `flows/`：流程模板、规则、片段及迁移映射资产。
- `scripts/`：校验、迁移、索引、发布结构验证脚本。
- `docs/`：用户文档、需求文档、设计文档与执行计划文档。
- `examples/`：示例 Godot 工程（用于本地验证）。
- `addons/`：仓库内维护的 Godot 插件源码。
- `godot_plugin_template/`：插件模板载荷（供安装/更新流程使用）。
- `tests/`：Python 测试与契约验证。
- `dist/`：本地产物目录（打包与元信息）。

## 三、入口与边界约定

- `默认 MCP 入口`：`install/start-mcp.ps1` -> `mcp/server.py`。
- `legacy MCP 子服务`：`tools/game-test-runner/mcp/server.py`，用于历史兼容与桥接，不作为默认用户入口。
- `版本事实源建议`：以 `mcp/version_manifest.json` 为权威，其他版本字段用于运行时或兼容校验。

## 四、非权威目录（本地临时）

以下目录用于本地更新、备份或多工作目录，不属于正式源码结构：

- `.mcp-backup-*`
- `.mcp-update-work-*`
- `.worktrees/`

这些目录已在 `.gitignore` 中忽略，不应纳入结构图与发布载荷。
详情见：`docs/local-temporary-directories.md`。

## 五、文档分层约定

- `docs/design/99-tools/`：长期设计与不变量说明。
- `docs/superpowers/plans/`：执行计划草案与阶段记录。
- `docs/authoritative-requirements/`：需求基线（权威需求来源）。

推荐先阅读：

1. `docs/quickstart.md`
2. `docs/configuration.md`
3. `docs/mcp-docs-index.md`

