param(
    [string]$PythonExe = "python",
    [string]$RepoRoot = "",
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$FlowId,
    [switch]$ValidateFigmaPipeline,
    [switch]$ValidateExecutionPipeline
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
$isBasicGameTestDesigned = ($seedJson.PSObject.Properties.Name -contains "flow_kind") -and ($seedJson.flow_kind -eq "basic_game_test")
if (-not $isBasicGameTestDesigned) {
    if ($seedJson.chat_protocol_mode -ne "three_phase") {
        throw "Seed flow chat_protocol_mode must be three_phase"
    }
    if ($seedJson.chat_contract_version -ne "v1") {
        throw "Seed flow chat_contract_version must be v1"
    }
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

if ($ValidateFigmaPipeline) {
    $compareFile = Get-ChildItem -LiteralPath $runtimeDir -File -Filter "compare_figma_game_ui_*.json" | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    $annotationFile = Get-ChildItem -LiteralPath $runtimeDir -File -Filter "ui_mismatch_annotations_*.json" | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    $approvalFile = Get-ChildItem -LiteralPath $runtimeDir -File -Filter "ui_fix_approval_*.json" | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    $suggestionFile = Get-ChildItem -LiteralPath $runtimeDir -File -Filter "ui_fix_suggestions_*.json" | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    $figmaBaselineEvent = Get-ChildItem -LiteralPath $runtimeDir -File -Filter "figma_baseline_last.json" | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if (-not $compareFile) { throw "Missing compare_figma_game_ui report in runtime dir" }
    if (-not $annotationFile) { throw "Missing ui_mismatch_annotations report in runtime dir" }
    if (-not $approvalFile) { throw "Missing ui_fix_approval report in runtime dir" }
    if (-not $suggestionFile) { throw "Missing ui_fix_suggestions report in runtime dir" }
    if (-not $figmaBaselineEvent) { throw "Missing figma_baseline_last event artifact in runtime dir" }

    $compareJson = Get-Content -LiteralPath $compareFile.FullName -Raw | ConvertFrom-Json
    $annotationJson = Get-Content -LiteralPath $annotationFile.FullName -Raw | ConvertFrom-Json
    $approvalJson = Get-Content -LiteralPath $approvalFile.FullName -Raw | ConvertFrom-Json
    $suggestionJson = Get-Content -LiteralPath $suggestionFile.FullName -Raw | ConvertFrom-Json

    foreach ($field in @("run_id", "figma_ref", "overall_status", "visual_diff", "layout_diff", "next_action")) {
        if (-not ($compareJson.PSObject.Properties.Name -contains $field)) {
            throw "compare report missing field: $field"
        }
    }
    if ($annotationJson.run_id -ne $compareJson.run_id) {
        throw "annotation run_id mismatch. compare=$($compareJson.run_id), annotation=$($annotationJson.run_id)"
    }
    if ($approvalJson.run_id -ne $compareJson.run_id) {
        throw "approval run_id mismatch. compare=$($compareJson.run_id), approval=$($approvalJson.run_id)"
    }
    if ($suggestionJson.run_id -ne $compareJson.run_id) {
        throw "suggestion run_id mismatch. compare=$($compareJson.run_id), suggestion=$($suggestionJson.run_id)"
    }
}

if ($ValidateExecutionPipeline) {
    $execLastPath = Join-Path $runtimeDir "basic_game_test_execution_last.json"
    if (-not (Test-Path -LiteralPath $execLastPath)) {
        throw "Missing basic_game_test_execution_last.json under runtime dir"
    }
    $execLastJson = Get-Content -LiteralPath $execLastPath -Raw | ConvertFrom-Json
    $executionReport = $execLastJson.execution_report
    if (-not $executionReport) {
        throw "basic_game_test_execution_last.json missing execution_report"
    }
    $phaseCoverage = $executionReport.phase_coverage
    if (-not $phaseCoverage) {
        throw "execution_report missing phase_coverage"
    }
    foreach ($phase in @("started", "result", "verify")) {
        if (-not ($phaseCoverage.PSObject.Properties.Name -contains $phase)) {
            throw "phase_coverage missing phase key: $phase"
        }
        try {
            $count = [int]$phaseCoverage.$phase
        }
        catch {
            throw "phase_coverage.$phase is not an integer"
        }
        if ($count -lt 1) {
            throw "phase_coverage.$phase must be >= 1 for execution pipeline validation, got $count"
        }
    }
    $flowRunReports = @(Get-ChildItem -LiteralPath $runtimeDir -File -Filter "flow_run_report_*.json" -ErrorAction Stop)
    $flowRunEvents = @(Get-ChildItem -LiteralPath $runtimeDir -File -Filter "flow_run_events_*.ndjson" -ErrorAction Stop)
    if ($flowRunReports.Count -lt 1) {
        throw "Missing flow_run_report_*.json under runtime dir"
    }
    if ($flowRunEvents.Count -lt 1) {
        throw "Missing flow_run_events_*.ndjson under runtime dir"
    }
}

Write-Output "[ASSERT] MCP artifacts validated."
Write-Output ("[ASSERT] index=" + $indexPath)
Write-Output ("[ASSERT] seed=" + $seedPath)
Write-Output ("[ASSERT] runtime_dir=" + $runtimeDir)
if ($ValidateFigmaPipeline) {
    Write-Output "[ASSERT] figma collaboration artifacts validated."
}
if ($ValidateExecutionPipeline) {
    Write-Output "[ASSERT] runtime execution pipeline artifacts validated."
}
