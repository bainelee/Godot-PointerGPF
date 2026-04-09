# PointerGPF Quickstart

## 1) 启动 MCP

release 包默认采用单目录载荷：`pointer_gpf/`。  
若你通过 release zip 安装，优先使用以下路径：

```powershell
powershell -ExecutionPolicy Bypass -File "pointer_gpf/install/start-mcp.ps1"
```

也可先做安装检查：

```powershell
powershell -ExecutionPolicy Bypass -File "pointer_gpf/install/install-mcp.ps1"
# or
powershell -ExecutionPolicy Bypass -File "pointer_gpf/install/install-mcp.ps1" -ConfigFile "D:/path/to/gtr.config.json"
```

查看版本通道：

```powershell
powershell -ExecutionPolicy Bypass -File "pointer_gpf/install/update-mcp.ps1" -CheckUpdateOnly
```

本地包更新（离线）：

```powershell
powershell -ExecutionPolicy Bypass -File "pointer_gpf/install/update-mcp.ps1" -PackageDir "D:/path/to/pointer_gpf_package"
```

远端包更新（发布后）：

```powershell
powershell -ExecutionPolicy Bypass -File "pointer_gpf/install/update-mcp.ps1" -ForceRemote
```

兼容入口：

- 仍可使用根目录 `pointer-gpf.cmd`，它会优先转发到 `pointer_gpf/install/pointer-gpf.ps1`。

更新行为说明（v0.2.4.3+）：

- `-ForceRemote` 优先级最高：即使本地 `mcp/version_manifest.json` 存在 `artifact.url`，也会优先解析 GitHub release 资产。
- 默认执行“仓库级关键同步”：`mcp/` + `gtr.config.json` + `godot_plugin_template/`。
- 如需仅更新 `mcp/`（不推荐），可附加 `-NoRootSync`。
- 成功日志会输出安装后真实版本（`installed_manifest_version` / `installed_runtime_version`）。
- 可用 `-FailOnVersionMismatch` 在版本不一致时直接失败（用于 CI/维护者校验）。
- 若同时使用 `-NoRootSync` 与 `-FailOnVersionMismatch`，脚本可能因根目录版本未同步而失败，这是预期保护行为。

如果仓库尚未发布 release，脚本会给出明确提示：
`No GitHub release found ... Publish release-package first.`

## 2) 在 Cursor 配置 MCP

```json
{
  "mcpServers": {
    "pointer-gpf": {
      "command": "C:/Users/your-user/AppData/Local/Programs/Python/Python311/python.exe",
      "args": [
        "-u",
        "D:/your-install-root/pointer_gpf/mcp/server.py",
        "--stdio"
      ]
    }
  }
}
```

可选：显式指定配置文件（覆盖默认）：

```powershell
python "mcp/server.py" --tool get_mcp_runtime_info --config-file "D:/path/to/gtr.config.json"
```

## 3) 安装 Godot 插件到目标项目

```powershell
python "mcp/server.py" --tool install_godot_plugin --project-root "D:/path/to/your/godot/project"
```

可选：仅启用（不重装）或强制更新：

```powershell
python "mcp/server.py" --tool enable_godot_plugin --project-root "D:/path/to/your/godot/project"
python "mcp/server.py" --tool update_godot_plugin --project-root "D:/path/to/your/godot/project"
```

一键链路（安装插件 + 初始化上下文）：

```powershell
powershell -ExecutionPolicy Bypass -File "install/install-plugin.ps1" -ProjectRoot "D:/path/to/your/godot/project"
# with explicit config
powershell -ExecutionPolicy Bypass -File "install/install-plugin.ps1" -ProjectRoot "D:/path/to/your/godot/project" -ConfigFile "D:/path/to/gtr.config.json"
```

## 4) 初始化项目理解文档

```powershell
python "mcp/server.py" --tool init_project_context --project-root "D:/path/to/your/godot/project" --max-files 2500
```

## 5) 刷新项目理解（增量）

```powershell
python "mcp/server.py" --tool refresh_project_context --project-root "D:/path/to/your/godot/project"
```

## 6) 生成 flow 草稿（seed）

```powershell
python "mcp/server.py" --tool generate_flow_seed --project-root "D:/path/to/your/godot/project" --flow-id "smoke_seed" --strategy "auto"
```

默认输出到 `pointer_gpf/generated_flows/<flow_id>.json`。
同时会记录运行时产物到 `pointer_gpf/gpf-exp/runtime/`。

## 6.5) 可执行基础流程：设计 + 运行 + 执行层校验

本链路面向 **通用 Godot 项目**。MCP 只定义执行契约与证据结构，不预设任何特定游戏剧情、系统或世界观。

与仅生成 seed 或跑通 `generate_flow_seed` 不同，下面链路会在 **Godot 运行时** 通过文件桥执行 flow，并用 `-ValidateExecutionPipeline` 校验 **执行层** 产物（执行报告、事件 NDJSON、三阶段覆盖等）。前提：已 `install_godot_plugin` 并启用插件，且**运行游戏**时 `runtime_bridge` 会处理 `pointer_gpf/tmp/command.json` → `response.json`（契约见 `docs/godot-adapter-contract-v1.md` 与 `mcp/adapter_contract_v1.json` 的 `runtime_bridge`）。

**1) 设计（生成基础测试 flow）**

```powershell
python "mcp/server.py" --tool design_game_basic_test_flow --project-root "D:/path/to/your/godot/project" --flow-id "basic_exec" --args "{""strategy"":""auto""}"
```

**2) 运行（MCP 执行；需游戏进程已启动）**

```powershell
python "mcp/server.py" --tool run_game_basic_test_flow --project-root "D:/path/to/your/godot/project" --flow-id "basic_exec" --args "{""step_timeout_ms"":30000,""fail_fast"":true,""shell_report"":true}"
```

**3) 断言（产物契约 + 执行层）**

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" `
  -ProjectRoot "D:/path/to/your/godot/project" `
  -FlowId "basic_exec" `
  -ValidateExecutionPipeline
```

`--strategy` 可选值：

- `auto`（默认）：按关键词自动挑选
- `ui`
- `exploration`（通用“区域推进/导航”策略标签，不绑定具体游戏）
- `builder`（通用“构建/布局”策略标签，不绑定具体游戏）
- `generic`

自然语言触发基础测试流程命令（推荐给 Agent 用户）：

```powershell
python "mcp/server.py" --tool design_game_basic_test_flow --project-root "D:/path/to/your/godot/project"
python "mcp/server.py" --tool update_game_basic_design_flow_by_current_state --project-root "D:/path/to/your/godot/project"
```

语义对应：

- `设计游戏基础测试流程` -> `design_game_basic_test_flow`
- `根据游戏当前状态,更新设计游戏基础设计流程` -> `update_game_basic_design_flow_by_current_state`

## 7) 查看适配契约

```powershell
python "mcp/server.py" --tool get_adapter_contract --args "{}"
```

## 8) 执行跨项目矩阵验证（本地）

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/verify-cross-project.ps1" `
  -TargetProjectRoot "D:/path/to/your/real/godot/project"
```

或设置环境变量后执行：

```powershell
$env:POINTER_GPF_TARGET_PROJECT_ROOT = "D:/path/to/your/real/godot/project"
powershell -ExecutionPolicy Bypass -File "scripts/verify-cross-project.ps1"
```

## 9) Figma 协同对比（标注 + 授权 + 修复建议）

先把 Figma 设计输出固化为基线（可由外部 Figma MCP 获取 `design_context` 和截图后传入）：

```powershell
python "mcp/server.py" --tool figma_design_to_baseline --args "{""project_root"":""D:/path/to/your/godot/project"",""figma_file_key"":""<fileKey>"",""figma_node_id"":""<nodeId>"",""figma_version"":""latest"",""figma_screenshot_file"":""D:/path/to/figma_node.png"",""figma_design_context"":{""frame"":{""width"":1920,""height"":1080}}}"
```

再执行对比与差异标注：

```powershell
python "mcp/server.py" --tool compare_figma_game_ui --args "{""project_root"":""D:/path/to/your/godot/project"",""figma_baseline_file"":""D:/path/to/figma_baseline.json"",""game_snapshot_file"":""D:/path/to/game_ui.png""}"
python "mcp/server.py" --tool annotate_ui_mismatch --args "{""project_root"":""D:/path/to/your/godot/project"",""compare_report_file"":""D:/path/to/compare_report.json""}"
```

授权后生成修复建议（未授权将拒绝）：

```powershell
python "mcp/server.py" --tool approve_ui_fix_plan --args "{""project_root"":""D:/path/to/your/godot/project"",""compare_report_file"":""D:/path/to/compare_report.json"",""approved"":true,""approval_token"":""review-approved-001""}"
python "mcp/server.py" --tool suggest_ui_fix_patch --args "{""project_root"":""D:/path/to/your/godot/project"",""compare_report_file"":""D:/path/to/compare_report.json"",""approval_file"":""D:/path/to/approval.json""}"
```

## 10) 执行产物契约校验（可选，推荐）

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" `
  -ProjectRoot "D:/path/to/your/godot/project" `
  -FlowId "smoke_seed"
```

若本次运行包含 Figma 协同链路，增加 `-ValidateFigmaPipeline`：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" `
  -ProjectRoot "D:/path/to/your/godot/project" `
  -FlowId "smoke_seed" `
  -ValidateFigmaPipeline
```

## 11) 迁移旧目录布局（可选）

如果目标项目里存在 `gameplayflow/*` 或根目录 `gpf-exp` 历史产物：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/migrate-legacy-layout.ps1" -ProjectRoot "D:/path/to/your/godot/project" -DryRun
# apply
powershell -ExecutionPolicy Bypass -File "scripts/migrate-legacy-layout.ps1" -ProjectRoot "D:/path/to/your/godot/project"
```

## 12) 发布后回填 manifest（维护者）

发布 zip 后可用以下命令更新 `mcp/version_manifest.json`：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/update-version-manifest.ps1" `
  -Version "0.2.4.3" `
  -ArtifactUrl "https://github.com/bainelee/Godot-PointerGPF/releases/download/v0.2.4.3/pointer-gpf-mcp-0.2.4.3.zip" `
  -Sha256 "<zip_sha256>" `
  -SizeBytes 123456
```

## 13) 更新链路冒烟（维护者）

建议每次改动 `install/update-mcp.ps1` 后执行：

```powershell
# 本地包模式冒烟（覆盖版本一致性检查）
powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" `
  -PackageDir "D:/AI/pointer_gpf" `
  -FailOnVersionMismatch

# 仅检查远端通道元数据
powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" -CheckUpdateOnly
```

生成的 flow seed 默认包含：

- `chat_protocol_mode: three_phase`
- `chat_contract_version: v1`
- 每个 step 的 `chat_contract.required_phases = [started, result, verify]`

文档会生成在：

- `pointer_gpf/project_context/01-project-overview.md`
- `pointer_gpf/project_context/02-runtime-architecture.md`
- `pointer_gpf/project_context/03-test-surface.md`
- `pointer_gpf/project_context/04-flow-authoring-guide.md`
- `pointer_gpf/project_context/05-flow-candidate-catalog.md`
- `pointer_gpf/project_context/index.json`

其中 `index.json` 会包含：

- `source_paths` / `source_counts`
- `script_signals` / `scene_signals`
- `data_signals`
- `flow_candidates`（action/assertion 候选）
- `todo_signals`
- `delta`（added/removed/changed）
- `confidence` 与 `unknowns`
