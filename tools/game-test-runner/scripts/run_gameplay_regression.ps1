# Legacy 入口：回归类 flow 的 CLI 包装（dry-run，不启动 Godot）。
# 用法：在仓库根目录执行：
#   powershell -ExecutionPolicy Bypass -File "tools/game-test-runner/scripts/run_gameplay_regression.ps1" -ProjectRoot "examples/godot_minimal"

param(
    [Parameter(Mandatory = $true)]
    [string] $ProjectRoot,
    [string] $FlowFile = "flows/internal/contract_force_fail_invalid_scene.json"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$flowAbs = if ([System.IO.Path]::IsPathRooted($FlowFile)) { $FlowFile } else { Join-Path $repo $FlowFile }
$env:MCP_ALLOW_NON_BROADCAST = "1"
$argsJson = (@{
        project_root = (Resolve-Path $ProjectRoot).Path
        flow_file    = $flowAbs
        dry_run      = $true
        allow_non_broadcast = $true
    } | ConvertTo-Json -Compress)

& python (Join-Path $repo "mcp\server.py") --tool run_game_flow --args $argsJson
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
