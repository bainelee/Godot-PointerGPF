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

$resolvedPython = $PythonExe
try {
    $pythonCmd = Get-Command $PythonExe -ErrorAction Stop | Select-Object -First 1
    if ($pythonCmd -and $pythonCmd.Source) {
        $resolvedPython = $pythonCmd.Source
    }
} catch {
    # Keep original value; runtime check below will fail with clear output if command is invalid.
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
Write-Output ('      "command": "' + $resolvedPython.Replace("\", "/") + '",')
$cursorArgs = @("-u", $serverPath.Replace("\", "/"), "--stdio")
if (-not [string]::IsNullOrWhiteSpace($ConfigFile)) {
    $cursorArgs += @("--config-file", $ConfigFile.Replace("\", "/"))
}
$cursorArgsJson = $cursorArgs | ConvertTo-Json -Compress
Write-Output ('      "args": ' + $cursorArgsJson)
Write-Output '    }'
Write-Output '  }'
Write-Output '}'
