param(
    [string]$PythonExe = "python",
    [string]$RepoRoot = "",
    [string]$ExampleProjectRoot = "",
    [string]$TargetProjectRoot = "",
    [int]$SmokeTimeoutSec = 180,
    [switch]$RunExecution
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
if ([string]::IsNullOrWhiteSpace($ExampleProjectRoot)) {
    $ExampleProjectRoot = Join-Path $RepoRoot "examples/godot_minimal"
}
if ([string]::IsNullOrWhiteSpace($TargetProjectRoot)) {
    $TargetProjectRoot = [Environment]::GetEnvironmentVariable("POINTER_GPF_TARGET_PROJECT_ROOT")
}
if ([string]::IsNullOrWhiteSpace($TargetProjectRoot)) {
    throw "TargetProjectRoot is required. Pass -TargetProjectRoot or set POINTER_GPF_TARGET_PROJECT_ROOT."
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
powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/assert-mcp-artifacts.ps1") -PythonExe $PythonExe -RepoRoot $RepoRoot -ProjectRoot $ExampleProjectRoot -FlowId "matrix_example_seed" | Out-Null

if ($RunExecution) {
    $flowIdExec = "matrix_example_exec"
    $tmpPy = Join-Path $env:TEMP ("mcp_verify_run_execution_" + [Guid]::NewGuid().ToString() + ".py")
    @'
import json
import os
import subprocess
import threading
import time
from pathlib import Path

repo_root = Path(os.environ["MCP_VERIFY_REPO"]).resolve()
project = Path(os.environ["MCP_VERIFY_PROJECT"]).resolve()
flow_id = os.environ.get("MCP_VERIFY_FLOW_ID", "matrix_example_exec").strip() or "matrix_example_exec"
python_exe = os.environ.get("MCP_VERIFY_PYTHON", "python")


def run_tool(name: str, args: dict) -> dict:
    cmd = [
        python_exe,
        str(repo_root / "mcp" / "server.py"),
        "--tool",
        name,
        "--args",
        json.dumps(args, ensure_ascii=False),
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{name} failed rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")
    payload = json.loads(proc.stdout)
    if not payload.get("ok"):
        raise RuntimeError(f"{name} error: {proc.stdout}")
    return payload["result"]


bridge = project / "pointer_gpf" / "tmp"
bridge.mkdir(parents=True, exist_ok=True)
last_seq = [None]


def respond() -> None:
    cmd_path = bridge / "command.json"
    rsp_path = bridge / "response.json"
    for _ in range(2000):
        if cmd_path.is_file():
            try:
                data = json.loads(cmd_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                time.sleep(0.02)
                continue
            seq = data.get("seq")
            if seq is None:
                time.sleep(0.02)
                continue
            if seq == last_seq[0]:
                time.sleep(0.02)
                continue
            last_seq[0] = int(seq)
            rsp_path.write_text(
                json.dumps(
                    {"ok": True, "seq": seq, "run_id": data.get("run_id"), "message": "ok"},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        time.sleep(0.02)


threading.Thread(target=respond, daemon=True).start()
run_tool(
    "design_game_basic_test_flow",
    {"project_root": str(project), "flow_id": flow_id, "max_feature_checks": 1},
)
run_tool(
    "run_game_basic_test_flow",
    {"project_root": str(project), "flow_id": flow_id, "step_timeout_ms": 8000},
)
'@ | Set-Content -LiteralPath $tmpPy -Encoding UTF8
    $env:MCP_VERIFY_REPO = $RepoRoot
    $env:MCP_VERIFY_PROJECT = $ExampleProjectRoot
    $env:MCP_VERIFY_FLOW_ID = $flowIdExec
    $env:MCP_VERIFY_PYTHON = $PythonExe
    try {
        & $PythonExe $tmpPy
        if ($LASTEXITCODE -ne 0) {
            throw "Execution pipeline helper failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue
        foreach ($k in @("MCP_VERIFY_REPO", "MCP_VERIFY_PROJECT", "MCP_VERIFY_FLOW_ID", "MCP_VERIFY_PYTHON")) {
            if (Test-Path -LiteralPath ("Env:\" + $k)) {
                Remove-Item -LiteralPath ("Env:\" + $k) -Force -ErrorAction SilentlyContinue
            }
        }
    }
    powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/assert-mcp-artifacts.ps1") -PythonExe $PythonExe -RepoRoot $RepoRoot -ProjectRoot $ExampleProjectRoot -FlowId $flowIdExec -ValidateExecutionPipeline | Out-Null
}

# Matrix B: target real project
Invoke-McpTool -Tool "check_plugin_status" -ProjectRoot $TargetProjectRoot | Out-Null
Invoke-McpTool -Tool "init_project_context" -ProjectRoot $TargetProjectRoot | Out-Null
Invoke-McpTool -Tool "generate_flow_seed" -ProjectRoot $TargetProjectRoot -FlowId "matrix_target_seed" | Out-Null
powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/assert-mcp-artifacts.ps1") -PythonExe $PythonExe -RepoRoot $RepoRoot -ProjectRoot $TargetProjectRoot -FlowId "matrix_target_seed" | Out-Null

$sw.Stop()
if ($sw.Elapsed.TotalSeconds -gt $SmokeTimeoutSec) {
    throw "Cross-project verification exceeded timeout. Actual=$($sw.Elapsed.TotalSeconds)s Limit=$SmokeTimeoutSec"
}

Write-Output "[VERIFY] cross-project matrix passed."
Write-Output ("[VERIFY] elapsed_sec=" + [Math]::Round($sw.Elapsed.TotalSeconds, 2))
