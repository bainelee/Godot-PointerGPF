param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [switch]$DryRun,
    [switch]$Overwrite
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ProjectRoot)) {
    throw "ProjectRoot not found: $ProjectRoot"
}

$projectRootAbs = (Resolve-Path -LiteralPath $ProjectRoot).Path
$migrations = @(
    @{
        Name = "legacy_project_context"
        Source = Join-Path $projectRootAbs "gameplayflow/project_context"
        Target = Join-Path $projectRootAbs "pointer_gpf/project_context"
    },
    @{
        Name = "legacy_generated_flows"
        Source = Join-Path $projectRootAbs "gameplayflow/generated_flows"
        Target = Join-Path $projectRootAbs "pointer_gpf/generated_flows"
    },
    @{
        Name = "legacy_gpf_exp"
        Source = Join-Path $projectRootAbs "gpf-exp"
        Target = Join-Path $projectRootAbs "pointer_gpf/gpf-exp"
    }
)

$ops = @()

function Add-Operation {
    param(
        [string]$Mode,
        [string]$SourcePath,
        [string]$TargetPath
    )
    $script:ops += @{
        mode = $Mode
        source = $SourcePath
        target = $TargetPath
    }
}

function Ensure-Dir {
    param([string]$PathValue)
    if (-not (Test-Path -LiteralPath $PathValue)) {
        New-Item -ItemType Directory -Path $PathValue -Force | Out-Null
    }
}

foreach ($m in $migrations) {
    $sourceDir = $m.Source
    $targetDir = $m.Target
    if (-not (Test-Path -LiteralPath $sourceDir)) {
        continue
    }
    Ensure-Dir -PathValue $targetDir

    $items = Get-ChildItem -LiteralPath $sourceDir -Force
    foreach ($item in $items) {
        $targetPath = Join-Path $targetDir $item.Name
        $exists = Test-Path -LiteralPath $targetPath
        if ($exists -and -not $Overwrite) {
            Add-Operation -Mode "skip_conflict" -SourcePath $item.FullName -TargetPath $targetPath
            continue
        }
        if ($exists -and $Overwrite) {
            Add-Operation -Mode "replace" -SourcePath $item.FullName -TargetPath $targetPath
            if (-not $DryRun) {
                Remove-Item -LiteralPath $targetPath -Recurse -Force
            }
        } else {
            Add-Operation -Mode "move" -SourcePath $item.FullName -TargetPath $targetPath
        }
        if (-not $DryRun) {
            Move-Item -LiteralPath $item.FullName -Destination $targetPath -Force
        }
    }

    # Remove empty legacy source directory after migration.
    if (-not $DryRun) {
        $remaining = Get-ChildItem -LiteralPath $sourceDir -Force -ErrorAction SilentlyContinue
        if (-not $remaining) {
            Remove-Item -LiteralPath $sourceDir -Recurse -Force
        }
    }
}

$status = if ($DryRun) { "dry_run" } else { "migrated" }
$report = @{
    status = $status
    project_root = $projectRootAbs
    operations = $ops
    overwrite = [bool]$Overwrite
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
}

$reportPath = Join-Path $projectRootAbs "pointer_gpf/reports/legacy_layout_migration_report.json"
if (-not $DryRun) {
    Ensure-Dir -PathValue (Split-Path -Parent $reportPath)
    ($report | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $reportPath -Encoding UTF8
}

Write-Output ("[MIGRATE] status=" + $status)
Write-Output ("[MIGRATE] operations=" + $ops.Count)
if (-not $DryRun) {
    Write-Output ("[MIGRATE] report=" + $reportPath)
}
