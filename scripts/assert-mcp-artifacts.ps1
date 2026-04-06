param(
    [string]$PythonExe = "python",
    [string]$RepoRoot = "",
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$FlowId
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}

$serverPath = Join-Path $RepoRoot "mcp/server.py"
if (-not (Test-Path -LiteralPath $serverPath)) {
    throw "Missing MCP server: $serverPath"
}

$resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

function Invoke-McpRuntimeInfo {
    $output = & $PythonExe $serverPath --tool get_mcp_runtime_info --project-root $resolvedProjectRoot --args "{}"
    if ($LASTEXITCODE -ne 0) {
        throw "get_mcp_runtime_info failed.`n$output"
    }
    $payload = $output | ConvertFrom-Json
    if (-not $payload.ok) {
        throw "get_mcp_runtime_info returned error: $($payload.error | ConvertTo-Json -Compress)"
    }
    return $payload.result
}

$runtime = Invoke-McpRuntimeInfo

$contextDir = Join-Path $resolvedProjectRoot $runtime.context_output_dir
$seedDir = Join-Path $resolvedProjectRoot $runtime.seed_flow_output_dir
$indexPath = Join-Path $contextDir "index.json"
$seedPath = Join-Path $seedDir ($FlowId + ".json")
$runtimeDir = $runtime.exp_runtime.exp_runtime_dir

if (-not (Test-Path -LiteralPath $indexPath)) {
    throw "Missing context index: $indexPath"
}
if (-not (Test-Path -LiteralPath $seedPath)) {
    throw "Missing seed flow: $seedPath"
}
if (-not (Test-Path -LiteralPath $runtimeDir)) {
    throw "Missing runtime dir: $runtimeDir"
}

$indexJson = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
$requiredIndexFields = @(
    "source_paths",
    "source_counts",
    "script_signals",
    "scene_signals",
    "data_signals",
    "flow_candidates",
    "todo_signals",
    "delta",
    "confidence",
    "unknowns"
)
foreach ($field in $requiredIndexFields) {
    if (-not ($indexJson.PSObject.Properties.Name -contains $field)) {
        throw "index.json missing field: $field"
    }
}

$seedJson = Get-Content -LiteralPath $seedPath -Raw | ConvertFrom-Json
if ($seedJson.chat_protocol_mode -ne "three_phase") {
    throw "Seed flow chat_protocol_mode must be three_phase"
}
if ($seedJson.chat_contract_version -ne "v1") {
    throw "Seed flow chat_contract_version must be v1"
}

$steps = @($seedJson.steps)
if ($steps.Count -eq 0) {
    throw "Seed flow has no steps: $seedPath"
}
foreach ($step in $steps) {
    if (-not $step.chat_contract) {
        throw "Seed flow step missing chat_contract"
    }
    $requiredPhases = @($step.chat_contract.required_phases)
    foreach ($phase in @("started", "result", "verify")) {
        if (-not ($requiredPhases -contains $phase)) {
            throw "Seed flow step missing required phase: $phase"
        }
    }
}

$runtimeFiles = Get-ChildItem -LiteralPath $runtimeDir -File -ErrorAction Stop
if ($runtimeFiles.Count -eq 0) {
    throw "Runtime dir has no files: $runtimeDir"
}

Write-Output "[ASSERT] MCP artifacts validated."
Write-Output ("[ASSERT] index=" + $indexPath)
Write-Output ("[ASSERT] seed=" + $seedPath)
Write-Output ("[ASSERT] runtime_dir=" + $runtimeDir)
