from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _hidden_popen(cmd: list[str], *, cwd: Path) -> subprocess.Popen[str]:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.Popen(cmd, **kwargs)


def _hidden_run(cmd: list[str], *, cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(cmd, **kwargs)


def _list_project_processes(project_root: Path) -> list[dict[str, Any]]:
    probe = (
        "$target = '{target}'; "
        "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object {{ $_.Name -like 'Godot*.exe' -and $_.CommandLine -match [regex]::Escape($target) }} | "
        "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    ).format(target=str(project_root.resolve()))
    proc = _hidden_run(["powershell", "-Command", probe], cwd=_repo_root())
    raw = proc.stdout.strip()
    if not raw:
        return []
    payload = json.loads(raw)
    if isinstance(payload, dict):
        payload = [payload]
    return payload if isinstance(payload, list) else []


def _kill_project_processes(project_root: Path) -> None:
    for item in _list_project_processes(project_root):
        pid = int(item.get("ProcessId", -1))
        if pid > 0:
            try:
                _hidden_run(["taskkill", "/PID", str(pid), "/T", "/F"], cwd=_repo_root(), timeout=30)
            except Exception:
                pass
    time.sleep(2)


def _clear_runtime_markers(project_root: Path) -> None:
    tmp_dir = project_root / "pointer_gpf" / "tmp"
    for name in (
        "flow_run.lock",
        "runtime_gate.json",
        "command.json",
        "response.json",
        "auto_enter_play_mode.flag",
        "auto_stop_play_mode.flag",
    ):
        (tmp_dir / name).unlink(missing_ok=True)


def _run_flow(project_root: Path, flow_file: Path, *, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    return _hidden_run(
        [
            sys.executable,
            "-m",
            "v2.mcp_core.server",
            "--tool",
            "run_basic_flow",
            "--project-root",
            str(project_root),
            "--flow-file",
            str(flow_file),
        ],
        cwd=_repo_root(),
        timeout=timeout,
    )


def _write_temp_conflict_flow() -> Path:
    payload = {
        "flowId": "lock_conflict_guard",
        "name": "Lock Conflict Guard",
        "steps": [
            {"id": "launch_game", "action": "launchGame"},
            {
                "id": "wait_missing",
                "action": "wait",
                "until": {"hint": "node_exists:DefinitelyMissingNode"},
                "timeoutMs": 15000,
            },
            {"id": "close_project", "action": "closeProject"},
        ],
    }
    fd, path = tempfile.mkstemp(prefix="pointer_gpf_v2_guard_", suffix=".json")
    os.close(fd)
    target = Path(path)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def run_conflict_check(project_root: Path) -> dict[str, Any]:
    _kill_project_processes(project_root)
    _clear_runtime_markers(project_root)
    flow_file = _write_temp_conflict_flow()
    try:
        first = _hidden_popen(
            [
                sys.executable,
                "-m",
                "v2.mcp_core.server",
                "--tool",
                "run_basic_flow",
                "--project-root",
                str(project_root),
                "--flow-file",
                str(flow_file),
            ],
            cwd=_repo_root(),
        )
        time.sleep(2)
        first_running = first.poll() is None
        second = _run_flow(project_root, _repo_root() / "v2" / "flows" / "basic_interactive_flow.json", timeout=120)
        first_stdout, first_stderr = first.communicate(timeout=60)
        return {
            "check": "conflict",
            "first_running_before_second": first_running,
            "second_returncode": second.returncode,
            "second_stdout": second.stdout.strip(),
            "second_stderr": second.stderr.strip(),
            "first_stdout": first_stdout.strip(),
            "first_stderr": first_stderr.strip(),
        }
    finally:
        flow_file.unlink(missing_ok=True)
        _kill_project_processes(project_root)
        _clear_runtime_markers(project_root)


def run_multi_editor_check(project_root: Path) -> dict[str, Any]:
    _kill_project_processes(project_root)
    _clear_runtime_markers(project_root)
    preflight = _hidden_run(
        [sys.executable, "-m", "v2.mcp_core.server", "--tool", "preflight_project", "--project-root", str(project_root)],
        cwd=_repo_root(),
        timeout=120,
    )
    preflight_payload = json.loads(preflight.stdout)
    executable = preflight_payload["result"]["checks"]["godot_executable"]
    primary = _hidden_popen([executable, "-e", "--path", str(project_root)], cwd=_repo_root())
    time.sleep(4)
    extra = _hidden_popen([executable, "-e", "--path", str(project_root)], cwd=_repo_root())
    time.sleep(2)
    try:
        flow = _run_flow(project_root, _repo_root() / "v2" / "flows" / "basic_interactive_flow.json", timeout=120)
        return {
            "check": "multi_editor",
            "primary_editor_pid": primary.pid,
            "extra_editor_pid": extra.pid,
            "returncode": flow.returncode,
            "stdout": flow.stdout.strip(),
            "stderr": flow.stderr.strip(),
        }
    finally:
        try:
            primary.terminate()
        except Exception:
            pass
        try:
            extra.terminate()
        except Exception:
            pass
        _kill_project_processes(project_root)
        _clear_runtime_markers(project_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify V2 runtime guard behavior without popping helper console windows.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--check", choices=("conflict", "multi-editor", "all"), default="all")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    checks = [args.check] if args.check != "all" else ["conflict", "multi-editor"]
    results = []
    for check in checks:
        if check == "conflict":
            results.append(run_conflict_check(project_root))
        elif check == "multi-editor":
            results.append(run_multi_editor_check(project_root))
    ok = True
    for item in results:
        payload = item.get("second_stdout", "") if item.get("check") == "conflict" else item.get("stdout", "")
        if item.get("check") == "conflict":
            ok = ok and bool(item.get("first_running_before_second")) and "FLOW_ALREADY_RUNNING" in payload
        elif item.get("check") == "multi-editor":
            ok = ok and "MULTIPLE_EDITOR_PROCESSES_DETECTED" in payload
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
