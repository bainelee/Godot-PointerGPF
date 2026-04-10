# Godot-PointerGPF

<p align="center">
  <img src="./pointer_gpf_logo.png" alt="PointerGPF 封面" width="780" />
</p>

**面向 Godot 灰盒自动化的开源 MCP 工具集。**  
通过一个 MCP 服务统一完成插件安装管理、项目上下文构建、flow seed 生成，以及 Figma 到游戏 UI 的验证闭环。

**简体中文** | [English](./README.md) | [快速开始](./docs/quickstart.md) | [更新日志](./CHANGELOG.md)

---

## 自动化边界（Windows）

**一次性人工准备（环境未就绪前不能省略）**

- 在 MCP 客户端（如 Cursor）中配置启动命令（见 `install/start-mcp.ps1` 输出的 `python -u …/mcp/server.py --stdio`）。
- 在目标 Godot 工程中按需启用 PointerGPF 插件。
- 使用文件桥时，需要编辑器/运行态能响应 `pointer_gpf/tmp`（详见运行门禁说明）。

**准备完成后可由代理/工具自动执行**

- 初始化或刷新项目上下文、生成与执行基础测试流程、自然语言路由、自动修复循环（在策略匹配时）等，无需为每一步再人工点一遍。

**仍建议保留人工决策的环节**

- UI 修复方案的批准（`approve_ui_fix_plan`）以及未工具化的产品层选择。

## 为什么使用 PointerGPF

很多 Godot 自动化流程分散在脚本、临时文档和编辑器手动操作中。PointerGPF 提供稳定的 MCP 接口，让编码代理可以：

- 在目标项目中安装/启用/更新插件
- 生成结构化项目画像（`project_context/index.json`）
- 基于真实代码/场景/数据信号生成 flow 初稿
- 执行带授权门禁的 Figma 基线对比与修复建议流程

这样可以把自动化流程沉淀为可复用、可追溯、可验证的工程能力。

## 当前能力（v0.3.0.0）

- 通用性约束：MCP 契约与工具设计面向全类型 Godot 项目，不绑定某一个具体游戏设定。
- 插件生命周期工具：`install_godot_plugin`、`enable_godot_plugin`、`update_godot_plugin`、`check_plugin_status`
- 项目上下文流水线：`init_project_context`、`refresh_project_context`、`generate_flow_seed`
- 自然语言触发命令：
  - `design_game_basic_test_flow`（触发词：`设计游戏基础测试流程`）
  - `update_game_basic_design_flow_by_current_state`（触发词：`根据游戏当前状态,更新设计游戏基础设计流程`）
- Figma 验证闭环：`figma_design_to_baseline`、`compare_figma_game_ui`、`annotate_ui_mismatch`、`approve_ui_fix_plan`、`suggest_ui_fix_patch`
- 契约与运行时诊断：`get_adapter_contract`、`get_mcp_runtime_info`
- 基础测试流程参照与用法（可读回 Markdown）：`get_basic_test_flow_reference_guide`（可与 `route_nl_intent` 配合；说明见 `docs/mcp-basic-test-flow-reference-usage.md`）
- 可执行基础流程：`design_game_basic_test_flow` → `run_game_basic_test_flow` / `run_game_basic_test_flow_by_current_state`（强制真实 `play_mode` + 逐步骤 shell 输出；文件桥 `pointer_gpf/tmp/command.json` ↔ `response.json`；引擎未开时自动拉起；**默认**失败后在限制内串联 `auto_fix_game_bug`，可用 `auto_repair: false` 或 `GPF_AUTO_REPAIR_DEFAULT=0` 关闭；可选 `GPF_REPAIR_BACKEND_CMD` 作为 L2）→ 可选 `scripts/assert-mcp-artifacts.ps1 -ValidateExecutionPipeline`
  - 每个阶段的 shell 播报固定为：
    - `[GPF-FLOW-TS] YYYY-MM-DD T HH:MM:SS`（本地系统时间）
    - 面向用户的中文语义行（`开始执行` / `执行结果` / `验证结论`）
  - 面向用户的播报中不显示技术字段（`run=` / `phase=` / `id=` / `action=` / `bridge_ok=` / `verified=`）。
  - 每次测试结束（通过/失败/超时/门禁失败）都必须执行关闭动作并输出 `project_close` 证据。`closeProject` 固定语义为 **结束带 `(DEBUG)` 的游戏测试会话**（与编辑器「停止运行」同类）；**默认保留 Godot 编辑器进程**。`examples/godot_minimal` 内 `addons/pointer_gpf` 与模板 `godot_plugin_template/addons/pointer_gpf/` **同源并纳入版本库**，避免示例工程长期跑旧插件。
- 自然语言路由与自动修复：`route_nl_intent`、`auto_fix_game_bug`（流程工具默认也会触发修复闭环，见 `docs/mcp-basic-test-flow-reference-usage.md`）
- 基础流程执行结论字段：`tool_usability`、`gameplay_runnability`、`step_broadcast_summary`
- Legacy gameplayflow（经根 MCP 桥接到 `tools/game-test-runner/mcp`）：`run_game_flow`、`start_stepwise_flow`、`pull_cursor_chat_plugin` 等；该部分用于历史兼容与回放，不代表单一游戏默认能力模型；CI 覆盖见 `.github/workflows/mcp-smoke.yml` / `mcp-integration.yml`；脚本入口见 `tools/game-test-runner/scripts/`
- 运行产物统一落盘到 `pointer_gpf/gpf-exp/runtime/`

## 支持的 MCP 客户端

PointerGPF 基于 stdio MCP，支持可启动本地命令的客户端，包括：

- Cursor
- Claude Code
- Codex CLI
- Windsurf / Gemini CLI（stdio 兼容模式）

## 快速开始

开始前建议先看目录边界说明：`docs/project-structure-baseline.md`。

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

维护者一键发版入口（以 `VERSION` 为单一版本源）：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/release.ps1" -DryRun
powershell -ExecutionPolicy Bypass -File "scripts/release.ps1"
```

说明：

- `update` 默认走远端 release 更新。
- `-ForceRemote` 现在具有最高优先级：即使本地清单含 `artifact.url`，也会优先解析 GitHub release 资产。
- 默认更新范围会同步 `mcp/`、`gtr.config.json`、`godot_plugin_template/`，避免版本漂移。
- 更新成功日志会输出实际安装版本（`installed_manifest_version`、`installed_runtime_version`），不再只显示更新前目标版本。
- 版本治理建议以 `mcp/version_manifest.json` 为权威来源，`gtr.config.json` 与运行时常量用于兼容与运行时校验。
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

你也可以直接通过自然语言触发基础测试流设计：

- `设计游戏基础测试流程` -> `design_game_basic_test_flow`
- `根据游戏当前状态,更新设计游戏基础设计流程` -> `update_game_basic_design_flow_by_current_state`
- `基础测试流程怎么用` / `流程预期说明` -> 先 `route_nl_intent` 再调用 `get_basic_test_flow_reference_guide`（全文与路径说明见 `docs/mcp-basic-test-flow-reference-usage.md`）

**你需要亲自动手（不可替代的人类操作）：**

- 检查 `pointer_gpf/project_context/` 里生成的文档是否合理。
- 在跑真实测试前，先确认 flow seed 是否符合你的测试意图。

### 3）Figma 到游戏 UI 对比闭环

**交给你的 Agent 执行：**

`figma_design_to_baseline -> compare_figma_game_ui -> annotate_ui_mismatch -> approve_ui_fix_plan -> suggest_ui_fix_patch`

**你需要亲自动手（不可替代的人类操作）：**

- 决定是否批准 UI 修复计划（这是人工授权门禁）。
- 在批准前，确认截图与基线确实对应同一版设计。

### 4）可执行基础测试流（文件桥）

**交给你的 Agent 执行：**

```powershell
python "mcp/server.py" --tool design_game_basic_test_flow --project-root "D:/path/to/your/godot/project" --flow-id "basic_exec" --args "{""strategy"":""auto""}"
python "mcp/server.py" --tool run_game_basic_test_flow --project-root "D:/path/to/your/godot/project" --flow-id "basic_exec" --args "{""step_timeout_ms"":30000,""fail_fast"":true,""shell_report"":true,""require_play_mode"":true}"
powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" -ProjectRoot "D:/path/to/your/godot/project" -FlowId "basic_exec" -ValidateExecutionPipeline
```

**你需要亲自动手（不可替代的人类操作）：**

- 确保目标项目可解析 Godot 可执行路径（`tools/game-test-runner/config/godot_executable.json`、工具参数或环境变量 `GODOT_EXE`/`GODOT_EDITOR_PATH`/`GODOT_PATH`）。

## 文档导航

- 目录职责与边界：[`docs/project-structure-baseline.md`](./docs/project-structure-baseline.md)
- MCP 文档导航：[`docs/mcp-docs-index.md`](./docs/mcp-docs-index.md)
- 快速开始：[`docs/quickstart.md`](./docs/quickstart.md)
- 配置说明：[`docs/configuration.md`](./docs/configuration.md)
- 适配契约：[`docs/godot-adapter-contract-v1.md`](./docs/godot-adapter-contract-v1.md)
- 采用指南：[`docs/adoption-overview.md`](./docs/adoption-overview.md)、[`docs/migration-checklist.md`](./docs/migration-checklist.md)
- 测试规范：[`docs/mcp-testing-spec.md`](./docs/mcp-testing-spec.md)
- Legacy gameplayflow 设计说明：[`docs/design/99-tools/11-godot-mcp-gameplay-flow-architecture.md`](./docs/design/99-tools/11-godot-mcp-gameplay-flow-architecture.md)、[`12-gameplay-flow-automation-roadmap.md`](./docs/design/99-tools/12-gameplay-flow-automation-roadmap.md)、[`13-gameplayflow-fix-loop-runbook.md`](./docs/design/99-tools/13-gameplayflow-fix-loop-runbook.md)、[`14-mcp-core-invariants.md`](./docs/design/99-tools/14-mcp-core-invariants.md)

## 开发与 CI

- 工作流：
  - `.github/workflows/mcp-smoke.yml`
  - `.github/workflows/mcp-integration.yml`
  - `.github/workflows/release-package.yml`
- 校验脚本：
  - `scripts/assert-mcp-artifacts.ps1`
  - `scripts/verify-cross-project.ps1`
  - `scripts/update-version-manifest.ps1`

## 许可证

见 [`LICENSE`](./LICENSE)。
