param(
    [string]$PythonExe = "python",
    [string]$ConfigFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$serverPath = Join-Path $repoRoot "mcp/server.py"
$manifestPath = Join-Path $repoRoot "mcp/version_manifest.json"

if (-not (Test-Path -LiteralPath $serverPath)) {
    throw "Missing MCP server: $serverPath"
}
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Missing version manifest: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$stableVersion = [string]$manifest.channels.stable.version

$cli = @($serverPath, "--tool", "get_mcp_runtime_info", "--args", "{}")
if (-not [string]::IsNullOrWhiteSpace($ConfigFile)) {
    $cli += @("--config-file", $ConfigFile)
}
$runtime = & $PythonExe @cli
if ($LASTEXITCODE -ne 0) {
    throw "MCP runtime check failed.`n$runtime"
}

Write-Output ("[INSTALL] pointer-gpf MCP version=" + $stableVersion)
Write-Output "[INSTALL] repository root: $repoRoot"
Write-Output "[INSTALL] next: run install/start-mcp.ps1 and configure Cursor MCP."
