from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


@dataclass
class HostActivityResult:
    activity: str
    started: bool
    iterations: int
    restored_position: list[int] | None
    window_probe_started: bool = False
    error: str = ""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_regression_module():
    path = _repo_root() / "scripts" / "verify-v2-regression.py"
    spec = importlib.util.spec_from_file_location("verify_v2_regression", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load regression helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cursor_position() -> tuple[int, int]:
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise OSError("GetCursorPos failed")
    return int(point.x), int(point.y)


def _set_cursor_position(x: int, y: int) -> None:
    if not ctypes.windll.user32.SetCursorPos(int(x), int(y)):
        raise OSError("SetCursorPos failed")


def _screen_size() -> tuple[int, int]:
    user32 = ctypes.windll.user32
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def _mouse_click() -> None:
    user32 = ctypes.windll.user32
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def _spawn_host_probe_window() -> subprocess.Popen[str]:
    command = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$form = New-Object System.Windows.Forms.Form; "
        "$form.Text = 'Pointer GPF Host Activity Probe'; "
        "$form.StartPosition = 'Manual'; "
        "$form.Location = New-Object System.Drawing.Point(40, 40); "
        "$form.Size = New-Object System.Drawing.Size(420, 240); "
        "$form.TopMost = $true; "
        "$label = New-Object System.Windows.Forms.Label; "
        "$label.Text = 'Host activity click probe'; "
        "$label.Dock = 'Fill'; "
        "$label.TextAlign = 'MiddleCenter'; "
        "$form.Controls.Add($label); "
        "$form.Add_Shown({ $form.Activate() }); "
        "[System.Windows.Forms.Application]::Run($form)"
    )
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "text": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0
    return subprocess.Popen(["powershell", "-Command", command], **kwargs)


def _mouse_wiggle_worker(stop_event: threading.Event, result: HostActivityResult) -> None:
    try:
        start_x, start_y = _cursor_position()
        width, height = _screen_size()
        amplitude = 24
        points = [
            (start_x, start_y),
            (min(width - 1, start_x + amplitude), start_y),
            (min(width - 1, start_x + amplitude), min(height - 1, start_y + amplitude)),
            (start_x, min(height - 1, start_y + amplitude)),
        ]
        result.started = True
        while not stop_event.is_set():
            px, py = points[result.iterations % len(points)]
            _set_cursor_position(px, py)
            result.iterations += 1
            time.sleep(0.05)
        _set_cursor_position(start_x, start_y)
        result.restored_position = [start_x, start_y]
    except Exception as exc:
        result.error = str(exc)


def _host_window_click_worker(stop_event: threading.Event, result: HostActivityResult) -> None:
    probe_process: subprocess.Popen[str] | None = None
    try:
        start_x, start_y = _cursor_position()
        probe_process = _spawn_host_probe_window()
        time.sleep(1.0)
        click_points = [(160, 160), (220, 160), (280, 160), (220, 200)]
        result.window_probe_started = probe_process.poll() is None
        result.started = True
        while not stop_event.is_set():
            px, py = click_points[result.iterations % len(click_points)]
            _set_cursor_position(px, py)
            _mouse_click()
            result.iterations += 1
            time.sleep(0.12)
        _set_cursor_position(start_x, start_y)
        result.restored_position = [start_x, start_y]
    except Exception as exc:
        result.error = str(exc)
    finally:
        if probe_process is not None and probe_process.poll() is None:
            try:
                probe_process.kill()
                probe_process.wait(timeout=5)
            except Exception:
                pass


def run_isolated_runtime_flow_with_host_activity(project_root: Path, flow_name: str, *, activity: str = "mouse_wiggle") -> dict[str, Any]:
    helper = _load_regression_module()
    helper._reset_runtime_state(project_root)
    flow_file = _repo_root() / "v2" / "flows" / flow_name
    stop_event = threading.Event()
    activity_result = HostActivityResult(
        activity=activity,
        started=False,
        iterations=0,
        restored_position=None,
    )
    worker_target = _mouse_wiggle_worker if activity == "mouse_wiggle" else _host_window_click_worker
    worker = threading.Thread(target=worker_target, args=(stop_event, activity_result), daemon=True)
    worker.start()
    try:
        proc = helper._hidden_run(
            [
                helper.sys.executable,
                "-m",
                "v2.mcp_core.server",
                "--tool",
                "run_basic_flow",
                "--project-root",
                str(project_root),
                "--flow-file",
                str(flow_file),
                "--execution-mode",
                "isolated_runtime",
            ],
            cwd=helper._repo_root(),
            timeout=240,
        )
    finally:
        stop_event.set()
        worker.join(timeout=5)
    payload = json.loads(proc.stdout)
    result = payload.get("result", {})
    ok = (
        proc.returncode == 0
        and bool(payload.get("ok"))
        and activity_result.started
        and not activity_result.error
        and activity_result.iterations > 0
        and (activity != "host_window_clicks" or activity_result.window_probe_started)
        and result.get("execution_mode") == "isolated_runtime"
        and result.get("isolation", {}).get("status") == "isolated_desktop"
        and result.get("isolation", {}).get("separate_desktop") is True
        and result.get("execution", {}).get("status") == "passed"
        and result.get("project_close", {}).get("status") == "verified"
    )
    return {
        "name": f"isolated_runtime_host_activity_{flow_file.stem}",
        "ok": ok,
        "returncode": proc.returncode,
        "payload": payload,
        "host_activity": {
            "activity": activity_result.activity,
            "started": activity_result.started,
            "iterations": activity_result.iterations,
            "restored_position": activity_result.restored_position,
            "window_probe_started": activity_result.window_probe_started,
            "error": activity_result.error,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate isolated runtime while the host desktop is actively receiving mouse movement.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--activity", choices=["mouse_wiggle", "host_window_clicks"], default="mouse_wiggle")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    results = [
        run_isolated_runtime_flow_with_host_activity(project_root, "basic_minimal_flow.json", activity=str(args.activity)),
        run_isolated_runtime_flow_with_host_activity(project_root, "basic_interactive_flow.json", activity=str(args.activity)),
    ]
    ok = all(item.get("ok", False) for item in results)
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
