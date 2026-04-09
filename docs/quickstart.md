# PointerGPF Quickstart

## 1) 启动 MCP

```powershell
powershell -ExecutionPolicy Bypass -File "install/start-mcp.ps1"
```

也可先做安装检查：

```powershell
powershell -ExecutionPolicy Bypass -File "install/install-mcp.ps1"
# or
powershell -ExecutionPolicy Bypass -File "install/install-mcp.ps1" -ConfigFile "D:/path/to/gtr.config.json"
```

查看版本通道：

```powershell
powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" -CheckUpdateOnly
```

本地包更新（离线）：

```powershell
powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" -PackageDir "D:/path/to/pointer_gpf_package"
```

远端包更新（发布后）：

```powershell
powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" -ForceRemote
```

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
        "D:/AI/pointer_gpf/mcp/server.py",
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

`--strategy` 可选值：

- `auto`（默认）：按关键词自动挑选
- `ui`
- `exploration`
- `builder`
- `generic`

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

## 12) 版本单一来源与一键发布（维护者）

**版本单一来源：** 仓库根目录的 `VERSION` 文件为版本号的唯一权威来源（四段式 `major.minor.patch.build`）。维护发版时请先在 `VERSION` 中写入目标版本；`scripts/sync-version.ps1` 会把该版本同步到插件与清单等受管文件。不要在与 `VERSION` 不一致的情况下手工改散处版本号。

**一键发布：** 在仓库根目录执行 `scripts/release.ps1`，会按 `VERSION` 同步版本、打与 CI 一致的 zip、`update-version-manifest.ps1` 回填下载地址与校验和，并（默认）提交、推送 `v*` 标签。**GitHub Release 与 zip 上传不再由本脚本默认执行**，推送 tag 后由 `.github/workflows/release-package.yml` 自动完成（避免与 CI 重复创建 release 的竞态）。无需为发版单独登录 `gh` CLI。

仅打印计划、不写文件、不跑 git/gh（演练）：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/release.ps1" -DryRun
```

正常发版（确认 `VERSION`、工作区干净、远程与凭证就绪后）：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/release.ps1"
```

预期日志（关键行）：

- 演练：`[RELEASE] version=<VERSION> tag=v<VERSION>`，并看到若干 `Would ...` 行；应出现说明 **不会** 本地 `gh release create`、由 **tag push 触发 CI 发布** 的提示
- 实发：推送 tag 后应看到由 **CI 负责 GitHub Release** 的说明，末尾仍为 `[RELEASE] Release pipeline finished.`

若只需同步版本 + 打包 + 更新 manifest，暂不提交/打标签/发 Release，可使用 `-PrepareOnly`（仍会写本地文件；与 `-DryRun` 同时指定时以 `-DryRun` 为准）。

**GitHub Actions 发布工作流：** `.github/workflows/release-package.yml` 以推送 **`v*`** 标签为主触发（与 `release.ps1` 推送的标签一致）。另支持 **`workflow_dispatch`** 手动触发：可填写 `version`，或从某一 **tag** 运行以复用该标签对应的版本；在分支上 dispatch 且未填版本时会失败，这是刻意约束。

**CI 分层：**

- **Smoke（`mcp-smoke.yml`）**：在 `main` 的 push/PR 上提供快反馈（短超时），覆盖安装/更新脚本、stdio、最小样例项目上下文与 Figma 闭环等。
- **Integration（`mcp-integration.yml`）**：按计划 **nightly**（cron）与 **`workflow_dispatch`** 手动运行；输入 **`quick`**（默认，小样本）或 **`full`**（仓库级上下文、产物校验、Figma 流水线与趋势报告产物）。日常开发以 smoke 为主；深度回归用 integration 的 **full** 或夜间任务。

## 13) 发布后回填 manifest（维护者，手工）

若未走 `scripts/release.ps1`，可在发布 zip 后用手工命令更新 `mcp/version_manifest.json`（`-Version` 须与根目录 `VERSION` 一致）：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/update-version-manifest.ps1" `
  -Version "0.2.4.3" `
  -ArtifactUrl "https://github.com/bainelee/Godot-PointerGPF/releases/download/v0.2.4.3/pointer-gpf-mcp-0.2.4.3.zip" `
  -Sha256 "<zip_sha256>" `
  -SizeBytes 123456
```

## 14) 更新链路冒烟（维护者）

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
