param(
    [string]$PythonExe = "python",
    [string]$RepoRoot = "",
    [string]$ExampleProjectRoot = "",
    [string]$TargetProjectRoot = "D:/GODOT_Test/old-archives-sp",
    [int]$SmokeTimeoutSec = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
if ([string]::IsNullOrWhiteSpace($ExampleProjectRoot)) {
    $ExampleProjectRoot = Join-Path $RepoRoot "examples/godot_minimal"
}

$serverPath = Join-Path $RepoRoot "mcp/server.py"
if (-not (Test-Path -LiteralPath $serverPath)) {
    throw "Missing MCP server: $serverPath"
}
if (-not (Test-Path -LiteralPath $ExampleProjectRoot)) {
    throw "Missing ExampleProjectRoot: $ExampleProjectRoot"
}
if (-not (Test-Path -LiteralPath $TargetProjectRoot)) {
    throw "Missing TargetProjectRoot: $TargetProjectRoot"
}

function Invoke-McpTool {
    param(
        [Parameter(Mandatory = $true)][string]$Tool,
        [string]$ProjectRoot = "",
        [string]$FlowId = ""
    )
    $args = @($serverPath, "--tool", $Tool)
    if (-not [string]::IsNullOrWhiteSpace($ProjectRoot)) {
        $args += @("--project-root", $ProjectRoot)
    }
    if (-not [string]::IsNullOrWhiteSpace($FlowId)) {
        $args += @("--flow-id", $FlowId)
    }
    $out = & $PythonExe @args
    if ($LASTEXITCODE -ne 0) {
        throw "Tool failed: $Tool`n$out"
    }
    return $out
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()

Invoke-McpTool -Tool "get_mcp_runtime_info" | Out-Null

# Matrix A: example project
Invoke-McpTool -Tool "install_godot_plugin" -ProjectRoot $ExampleProjectRoot | Out-Null
Invoke-McpTool -Tool "check_plugin_status" -ProjectRoot $ExampleProjectRoot | Out-Null
Invoke-McpTool -Tool "init_project_context" -ProjectRoot $ExampleProjectRoot | Out-Null
Invoke-McpTool -Tool "generate_flow_seed" -ProjectRoot $ExampleProjectRoot -FlowId "matrix_example_seed" | Out-Null

# Matrix B: target real project
Invoke-McpTool -Tool "check_plugin_status" -ProjectRoot $TargetProjectRoot | Out-Null
Invoke-McpTool -Tool "init_project_context" -ProjectRoot $TargetProjectRoot | Out-Null
Invoke-McpTool -Tool "generate_flow_seed" -ProjectRoot $TargetProjectRoot -FlowId "matrix_target_seed" | Out-Null

$sw.Stop()
if ($sw.Elapsed.TotalSeconds -gt $SmokeTimeoutSec) {
    throw "Cross-project verification exceeded timeout. Actual=$($sw.Elapsed.TotalSeconds)s Limit=$SmokeTimeoutSec"
}

Write-Output "[VERIFY] cross-project matrix passed."
Write-Output ("[VERIFY] elapsed_sec=" + [Math]::Round($sw.Elapsed.TotalSeconds, 2))
