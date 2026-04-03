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

如果仓库尚未发布 release，脚本会给出明确提示：
`No GitHub release found ... Publish release-package first.`

## 2) 在 Cursor 配置 MCP

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

默认输出到 `gameplayflow/generated_flows/<flow_id>.json`。

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
powershell -ExecutionPolicy Bypass -File "scripts/verify-cross-project.ps1"
```

## 9) 发布后回填 manifest（维护者）

发布 zip 后可用以下命令更新 `mcp/version_manifest.json`：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/update-version-manifest.ps1" `
  -Version "0.2.1" `
  -ArtifactUrl "https://github.com/bainelee/Godot-PointerGPF/releases/download/v0.2.1/pointer-gpf-mcp-0.2.1.zip" `
  -Sha256 "<zip_sha256>" `
  -SizeBytes 123456
```

生成的 flow seed 默认包含：

- `chat_protocol_mode: three_phase`
- `chat_contract_version: v1`
- 每个 step 的 `chat_contract.required_phases = [started, result, verify]`

文档会生成在：

- `gameplayflow/project_context/01-project-overview.md`
- `gameplayflow/project_context/02-runtime-architecture.md`
- `gameplayflow/project_context/03-test-surface.md`
- `gameplayflow/project_context/04-flow-authoring-guide.md`
- `gameplayflow/project_context/05-flow-candidate-catalog.md`
- `gameplayflow/project_context/index.json`

其中 `index.json` 会包含：

- `source_paths` / `source_counts`
- `script_signals` / `scene_signals`
- `data_signals`
- `flow_candidates`（action/assertion 候选）
- `todo_signals`
- `delta`（added/removed/changed）
- `confidence` 与 `unknowns`
