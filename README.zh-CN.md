# Godot-PointerGPF

<p align="center">
  <img src="./pointer_gpf_logo.png" alt="PointerGPF 封面" width="780" />
</p>

**面向 Godot 灰盒自动化的开源 MCP 工具集。**  
通过一个 MCP 服务统一完成插件安装管理、项目上下文构建、flow seed 生成，以及 Figma 到游戏 UI 的验证闭环。

**简体中文** | [English](./README.md) | [快速开始](./docs/quickstart.md) | [更新日志](./CHANGELOG.md)

---

## 为什么使用 PointerGPF

很多 Godot 自动化流程分散在脚本、临时文档和编辑器手动操作中。PointerGPF 提供稳定的 MCP 接口，让编码代理可以：

- 在目标项目中安装/启用/更新插件
- 生成结构化项目画像（`project_context/index.json`）
- 基于真实代码/场景/数据信号生成 flow 初稿
- 执行带授权门禁的 Figma 基线对比与修复建议流程

这样可以把自动化流程沉淀为可复用、可追溯、可验证的工程能力。

## 当前能力（v0.2.4.5）

- 插件生命周期工具：`install_godot_plugin`、`enable_godot_plugin`、`update_godot_plugin`、`check_plugin_status`
- 项目上下文流水线：`init_project_context`、`refresh_project_context`、`generate_flow_seed`
- Figma 验证闭环：`figma_design_to_baseline`、`compare_figma_game_ui`、`annotate_ui_mismatch`、`approve_ui_fix_plan`、`suggest_ui_fix_patch`
- 契约与运行时诊断：`get_adapter_contract`、`get_mcp_runtime_info`
- 运行产物统一落盘到 `pointer_gpf/gpf-exp/runtime/`

## 支持的 MCP 客户端

PointerGPF 基于 stdio MCP，支持可启动本地命令的客户端，包括：

- Cursor
- Claude Code
- Codex CLI
- Windsurf / Gemini CLI（stdio 兼容模式）

## 快速开始

### 1）交给你的 Agent 执行

先让 Agent 阅读这些文件：

- `docs/quickstart.md`（安装、更新、迁移命令）
- `docs/configuration.md`（配置项和输出目录）

然后让 Agent 按顺序执行：

1. 本地启动检查：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "install/start-mcp.ps1"
   ```
2. 运行时信息自检：
   ```powershell
   python "mcp/server.py" --tool get_mcp_runtime_info --args "{}"
   ```
3. 如果你有 Godot 项目，执行插件安装：
   ```powershell
   python "mcp/server.py" --tool install_godot_plugin --project-root "D:/path/to/your/godot/project"
   ```

### 2）你需要亲自动手（不可替代的人类操作）

下面这些步骤必须你在 IDE 里手动完成：

1. 打开 Cursor 的 MCP 设置，新增或编辑服务配置。
2. 粘贴以下配置：

   ```json
   {
     "mcpServers": {
       "pointer-gpf": {
         "command": "C:/Users/your-user/AppData/Local/Programs/Python/Python311/python.exe",
         "args": [
           "-u",
           "D:/AI/pointer_gpf/mcp/server.py",
           "--stdio"
         ]
       }
     }
   }
   ```

3. 在 MCP 面板里打开 `pointer-gpf` 开关。
4. 确认左侧状态点为绿色，并且工具列表可见。

如果状态点为红色，请先重启 Cursor，再重新执行 `install/start-mcp.ps1`。

## 更新（Updating）

推荐用这种“命令式”更新方式：

```powershell
.\pointer-gpf.cmd update
```

仅检查是否有新版本：

```powershell
.\pointer-gpf.cmd check
```

说明：

- `update` 默认走远端 release 更新。
- `-ForceRemote` 现在具有最高优先级：即使本地清单含 `artifact.url`，也会优先解析 GitHub release 资产。
- 默认更新范围会同步 `mcp/`、`gtr.config.json`、`godot_plugin_template/`，避免版本漂移。
- 更新成功日志会输出实际安装版本（`installed_manifest_version`、`installed_runtime_version`），不再只显示更新前目标版本。
- 如果你有本地离线包，可以用：

```powershell
powershell -ExecutionPolicy Bypass -File "install/pointer-gpf.ps1" update -PackageDir "D:/path/to/pointer_gpf_package"
```

## 核心工作流

### 1）目标项目插件安装

**交给你的 Agent 执行：**

```powershell
python "mcp/server.py" --tool install_godot_plugin --project-root "D:/path/to/your/godot/project"
```

**你需要亲自动手（不可替代的人类操作）：**

- 打开 Godot 编辑器，确认插件在项目设置中已启用。
- 确认目标项目内存在 `addons/pointer_gpf` 目录。

### 2）项目画像与 flow seed 生成

**交给你的 Agent 执行：**

```powershell
python "mcp/server.py" --tool init_project_context --project-root "D:/path/to/your/godot/project" --max-files 2500
python "mcp/server.py" --tool generate_flow_seed --project-root "D:/path/to/your/godot/project" --flow-id "smoke_seed" --strategy "auto"
```

**你需要亲自动手（不可替代的人类操作）：**

- 检查 `pointer_gpf/project_context/` 里生成的文档是否合理。
- 在跑真实测试前，先确认 flow seed 是否符合你的测试意图。

### 3）Figma 到游戏 UI 对比闭环

**交给你的 Agent 执行：**

`figma_design_to_baseline -> compare_figma_game_ui -> annotate_ui_mismatch -> approve_ui_fix_plan -> suggest_ui_fix_patch`

**你需要亲自动手（不可替代的人类操作）：**

- 决定是否批准 UI 修复计划（这是人工授权门禁）。
- 在批准前，确认截图与基线确实对应同一版设计。

## 文档导航

- 快速开始：[`docs/quickstart.md`](./docs/quickstart.md)
- 配置说明：[`docs/configuration.md`](./docs/configuration.md)
- 适配契约：[`docs/godot-adapter-contract-v1.md`](./docs/godot-adapter-contract-v1.md)
- 采用指南：[`docs/adoption-overview.md`](./docs/adoption-overview.md)、[`docs/migration-checklist.md`](./docs/migration-checklist.md)
- 测试规范：[`docs/mcp-testing-spec.md`](./docs/mcp-testing-spec.md)

## 开发与 CI

- **版本单一来源：** 仓库根目录 `VERSION`（四段式 `major.minor.patch.build`）。发版流程以该文件为准；`scripts/sync-version.ps1`（由 `scripts/release.ps1` 调用）将版本同步到各受管文件，避免多处手工改版本号导致漂移。
- **一键发布（维护者）：** 在仓库根目录执行 `scripts/release.ps1`。加 `-DryRun` 仅打印计划，不写文件、不执行 git/GitHub。正常执行会同步版本、打与 CI 一致的 zip、更新 `mcp/version_manifest.json`、提交并推送 **`v*`** 标签。**GitHub Release 由 CI 在推送 tag 后创建**（`.github/workflows/release-package.yml`），脚本默认不再本地执行 `gh release create`，以免与工作流竞态。
- **发布工作流：** `.github/workflows/release-package.yml` 以推送 **`v*`** 标签为主触发；另可选 **`workflow_dispatch`** 手动触发（可填写 `version`，或从 tag 运行以对应版本）。
- **CI 分层：** **`mcp-smoke.yml`** 在 `main` 的 push/PR 上提供快反馈（短超时）。**`mcp-integration.yml`** 由 **nightly** 定时与 **`workflow_dispatch`** 触发，校验范围可选 **`quick`**（小样本）与 **`full`**（仓库级、Figma 流水线、趋势报告产物）。
- 工作流：
  - `.github/workflows/mcp-smoke.yml`
  - `.github/workflows/mcp-integration.yml`
  - `.github/workflows/release-package.yml`
- 校验脚本：
  - `scripts/assert-mcp-artifacts.ps1`
  - `scripts/verify-cross-project.ps1`
  - `scripts/update-version-manifest.ps1`
  - `scripts/release.ps1`

## 许可证

见 [`LICENSE`](./LICENSE)。
