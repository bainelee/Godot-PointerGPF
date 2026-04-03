param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [string]$PythonExe = "python",
    [string]$ConfigFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$serverPath = Join-Path $repoRoot "mcp/server.py"

if (-not (Test-Path -LiteralPath $serverPath)) {
    throw "Missing MCP server: $serverPath"
}
if (-not (Test-Path -LiteralPath $ProjectRoot)) {
    throw "ProjectRoot not found: $ProjectRoot"
}

$installCli = @($serverPath, "--tool", "install_godot_plugin", "--project-root", $ProjectRoot)
if (-not [string]::IsNullOrWhiteSpace($ConfigFile)) {
    $installCli += @("--config-file", $ConfigFile)
}
$installOut = & $PythonExe @installCli
if ($LASTEXITCODE -ne 0) {
    throw "install_godot_plugin failed.`n$installOut"
}

$ctxCli = @($serverPath, "--tool", "init_project_context", "--project-root", $ProjectRoot)
if (-not [string]::IsNullOrWhiteSpace($ConfigFile)) {
    $ctxCli += @("--config-file", $ConfigFile)
}
$ctxOut = & $PythonExe @ctxCli
if ($LASTEXITCODE -ne 0) {
    throw "init_project_context failed.`n$ctxOut"
}

Write-Output "[INSTALL] plugin installed and project context initialized."
