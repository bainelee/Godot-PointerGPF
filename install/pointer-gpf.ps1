param(
    [Parameter(Position = 0)]
    [ValidateSet("update", "check", "start", "help")]
    [string]$Command = "help",
    [string]$PackageDir = "",
    [string]$ConfigFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$updateScript = Join-Path $repoRoot "install/update-mcp.ps1"
$startScript = Join-Path $repoRoot "install/start-mcp.ps1"

switch ($Command) {
    "update" {
        $args = @("-ExecutionPolicy", "Bypass", "-File", $updateScript)
        if (-not [string]::IsNullOrWhiteSpace($PackageDir)) {
            $args += @("-PackageDir", $PackageDir)
        } else {
            $args += @("-ForceRemote")
        }
        & powershell @args
        exit $LASTEXITCODE
    }
    "check" {
        & powershell -ExecutionPolicy Bypass -File $updateScript -CheckUpdateOnly
        exit $LASTEXITCODE
    }
    "start" {
        $args = @("-ExecutionPolicy", "Bypass", "-File", $startScript)
        if (-not [string]::IsNullOrWhiteSpace($ConfigFile)) {
            $args += @("-ConfigFile", $ConfigFile)
        }
        & powershell @args
        exit $LASTEXITCODE
    }
    default {
        Write-Output "PointerGPF command helper"
        Write-Output ""
        Write-Output "Usage:"
        Write-Output "  powershell -ExecutionPolicy Bypass -File `"install/pointer-gpf.ps1`" update"
        Write-Output "  powershell -ExecutionPolicy Bypass -File `"install/pointer-gpf.ps1`" check"
        Write-Output "  powershell -ExecutionPolicy Bypass -File `"install/pointer-gpf.ps1`" start"
        Write-Output ""
        Write-Output "Options:"
        Write-Output "  update -PackageDir `"D:/path/to/package`"   # local package update"
        Write-Output "  start  -ConfigFile `"D:/path/to/gtr.config.json`""
        exit 0
    }
}
