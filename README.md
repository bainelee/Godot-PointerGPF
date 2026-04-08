# Godot-PointerGPF

一个面向 Godot 开发的自动化灰盒测试工具（MCP 入口 + 插件安装 + 项目初始化理解）。

## 当前可用能力（v0.2.2）

- `install_godot_plugin`：向目标 Godot 项目安装 `addons/pointer_gpf` 并写入 `project.godot` 插件启用项。
- `enable_godot_plugin`：在插件已存在时，仅执行启用写入。
- `update_godot_plugin`：覆盖更新插件文件并确保启用。
- `check_plugin_status`：检查插件文件和启用状态。
- `get_adapter_contract`：返回 Godot Adapter Contract v1（机器可读 JSON）。
- `init_project_context`：首次扫描项目并生成 `pointer_gpf/project_context/` 权威文档。
- `refresh_project_context`：增量刷新项目画像文档。
- 初始化输出包含 `flow_candidates`（动作/断言候选），可作为自然语言生成 flow 的直接参考。
- `generate_flow_seed`：基于 `project_context/index.json` 生成首版 flow 草稿（JSON）。
  - 支持 `strategy=auto/ui/exploration/builder/generic` 模板策略。
- `figma_design_to_baseline`：把 Figma 设计上下文+截图固化为可追溯基线（含 `fileKey/nodeId/version`）。
- `compare_figma_game_ui`：对比 Figma 基线与游戏截图，输出视觉+结构化差异报告。
- `annotate_ui_mismatch`：把差异报告转为可审阅 mismatch 列表。
- `approve_ui_fix_plan`：记录修复授权门禁（未授权禁止进入建议修复）。
- `suggest_ui_fix_patch`：基于差异与授权生成修复建议草稿（默认不自动写回）。

## 启动 MCP（本地）

```powershell
powershell -ExecutionPolicy Bypass -File "install/start-mcp.ps1"
```

完整步骤见：`docs/quickstart.md`

默认配置文件：`gtr.config.json`  
可在目标项目根目录放置同名文件覆盖默认配置，或通过 `--config-file` 显式指定。
默认会把 MCP 产物收敛在目标项目的 `pointer_gpf/` 主目录下（`project_context/`、`generated_flows/`、`reports/`、`gpf-exp/`）。
运行时会在 `pointer_gpf/gpf-exp/runtime/` 写入最近执行产物与事件日志（`*.json` + `events.ndjson`）。

## Cursor MCP 配置示例

```json
{
  "mcpServers": {
    "pointer-gpf": {
      "command": "python",
      "args": [
        "D:/AI/pointer_gpf/mcp/server.py"
      ]
    }
  }
}
```

## MCP 调用示例

安装插件：

```powershell
python "mcp/server.py" --tool install_godot_plugin --project-root "D:/path/to/your/godot/project"
```

初始化项目理解：

```powershell
python "mcp/server.py" --tool init_project_context --project-root "D:/path/to/your/godot/project" --max-files 2500
```

增量刷新项目理解：

```powershell
python "mcp/server.py" --tool refresh_project_context --project-root "D:/path/to/your/godot/project"
```

## CI

- GitHub Actions: `.github/workflows/mcp-smoke.yml`
- 覆盖：`install-mcp.ps1`、CLI runtime info、stdio protocol `initialize/tools/list/tools/call`（含负例）、`init_project_context`、`generate_flow_seed`（最小样本）
- 覆盖 Figma 协同最小链路：`figma_design_to_baseline -> compare_figma_game_ui -> annotate_ui_mismatch -> approve_ui_fix_plan -> suggest_ui_fix_patch`
- 产物契约断言：`scripts/assert-mcp-artifacts.ps1`（`index.json`、seed flow chat contract、runtime 产物）
- Job 预算：`timeout-minutes: 2`，并对关键上下文步骤设置 90s 阈值
- Integration: `.github/workflows/mcp-integration.yml`（`workflow_dispatch` + nightly，仓库规模 `max-files=2500`，输出趋势报告 artifact）
- 跨项目矩阵脚本：`scripts/verify-cross-project.ps1`（需显式 `-TargetProjectRoot` 或环境变量 `POINTER_GPF_TARGET_PROJECT_ROOT`）
- 旧目录迁移脚本：`scripts/migrate-legacy-layout.ps1`（支持 `-DryRun`）
- 发布回填脚本：`scripts/update-version-manifest.ps1`
- 测试规范：`docs/mcp-testing-spec.md`

## Adapter Contract

- 文档：`docs/godot-adapter-contract-v1.md`
- JSON：`mcp/adapter_contract_v1.json`

## Changelog

- `CHANGELOG.md`

## Adoption Docs

- `docs/adoption-overview.md`
- `docs/migration-checklist.md`
- `docs/legacy-entry-blocking-and-rollback.md`
- `docs/configuration.md`
