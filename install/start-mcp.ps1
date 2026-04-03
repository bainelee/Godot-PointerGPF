param(
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

$cli = @($serverPath, "--tool", "get_mcp_runtime_info", "--args", "{}")
if (-not [string]::IsNullOrWhiteSpace($ConfigFile)) {
    $cli += @("--config-file", $ConfigFile)
}
$runtime = & $PythonExe @cli
if ($LASTEXITCODE -ne 0) {
    throw "Runtime check failed.`n$runtime"
}

Write-Output "[MCP] pointer-gpf ready."
Write-Output "[MCP] Cursor settings snippet:"
Write-Output '{'
Write-Output '  "mcpServers": {'
Write-Output '    "pointer-gpf": {'
Write-Output '      "command": "python",'
$argsLine = @('"' + $serverPath.Replace("\", "/") + '"')
if (-not [string]::IsNullOrWhiteSpace($ConfigFile)) {
    $argsLine += '"' + "--config-file" + '"'
    $argsLine += '"' + $ConfigFile.Replace("\", "/") + '"'
}
Write-Output ('      "args": [' + ($argsLine -join ", ") + ']')
Write-Output '    }'
Write-Output '  }'
Write-Output '}'
