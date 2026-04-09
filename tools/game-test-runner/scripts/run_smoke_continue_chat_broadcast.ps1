# Legacy 入口：chat 播报相关 smoke flow（需真实 Godot + 测试驱动；此处仅打印约定路径）。
# Flow 资产：`flows/suites/regression/gameplay/smoke_continue_chat_broadcast.json`
# 执行应通过 MCP `run_game_flow` / `start_cursor_chat_plugin` + `pull_cursor_chat_plugin`，而非仅本脚本。

param(
    [string] $ProjectRoot = "examples/godot_minimal"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$flowRel = "flows/suites/regression/gameplay/smoke_continue_chat_broadcast.json"
$flowAbs = Join-Path $repo $flowRel
Write-Host "[run_smoke_continue_chat_broadcast] repo=$repo"
Write-Host "[run_smoke_continue_chat_broadcast] project=$ProjectRoot flow=$flowAbs"
Write-Host "Invoke example: python mcp/server.py --tool start_cursor_chat_plugin --args '{\"project_root\":\"...\",\"flow_file\":\"$flowRel\"}'"
