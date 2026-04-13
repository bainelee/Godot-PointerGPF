from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable


def list_project_processes(
    project_root: Path,
    *,
    subprocess_run: Callable[..., Any] = subprocess.run,
) -> list[dict[str, Any]]:
    target = str(project_root.resolve())
    probe = (
        "$target = '{target}'; "
        "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object {{ $_.Name -like 'Godot*.exe' -and $_.CommandLine -match [regex]::Escape($target) }} | "
        "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    ).format(target=target)
    result = subprocess_run(
        ["powershell", "-Command", probe],
        capture_output=True,
        text=True,
        timeout=10,
    )
    raw = result.stdout.strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            out.append(item)
    return out


def is_pid_running(
    pid: int,
    *,
    subprocess_run: Callable[..., Any] = subprocess.run,
) -> bool:
    if pid <= 0:
        return False
    probe = f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Id"
    result = subprocess_run(
        ["powershell", "-Command", probe],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return bool(result.stdout.strip())


def list_project_editor_processes(
    project_root: Path,
    *,
    list_project_processes: Callable[[Path], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in list_project_processes(project_root):
        command_line = str(item.get("CommandLine", ""))
        if " -e " in f" {command_line} ":
            out.append(item)
    return out


def is_editor_process_running(
    project_root: Path,
    *,
    list_project_editor_processes: Callable[[Path], list[dict[str, Any]]],
) -> bool:
    return bool(list_project_editor_processes(project_root))


def detect_multiple_project_processes(
    project_root: Path,
    *,
    list_project_editor_processes: Callable[[Path], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    processes = list_project_editor_processes(project_root)
    if len(processes) <= 1:
        return None
    return {
        "status": "multiple_editors_detected",
        "project_process_count": len(processes),
        "project_processes": processes,
        "message": "close extra Godot editor instances for this project before running a flow",
    }
