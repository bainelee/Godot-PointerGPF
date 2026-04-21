from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable


def flow_lock_path(bridge_dir: Callable[[Path], Path], project_root: Path) -> Path:
    return bridge_dir(project_root) / "flow_run.lock"


def read_flow_lock(
    project_root: Path,
    *,
    flow_lock_path: Callable[[Path], Path],
) -> dict[str, Any]:
    lock_path = flow_lock_path(project_root)
    if not lock_path.is_file():
        return {}
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def release_flow_lock(
    project_root: Path,
    token: str,
    *,
    flow_lock_path: Callable[[Path], Path],
    read_flow_lock: Callable[[Path], dict[str, Any]],
) -> None:
    lock_path = flow_lock_path(project_root)
    payload = read_flow_lock(project_root)
    if payload.get("token") != token:
        return
    lock_path.unlink(missing_ok=True)


def acquire_flow_lock(
    project_root: Path,
    *,
    flow_lock_path: Callable[[Path], Path],
    read_flow_lock: Callable[[Path], dict[str, Any]],
    is_pid_running: Callable[[int], bool],
) -> dict[str, Any]:
    lock_path = flow_lock_path(project_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_flow_lock(project_root)
    pid = os.getpid()
    current_token = uuid.uuid4().hex
    recovered_stale_lock = False
    stale_lock: dict[str, Any] | None = None
    if existing:
        existing_pid = int(existing.get("pid", -1))
        if is_pid_running(existing_pid):
            raise RuntimeError(json.dumps(existing, ensure_ascii=False))
        if existing_pid > 0:
            recovered_stale_lock = True
            stale_lock = existing
        lock_path.unlink(missing_ok=True)
    payload = {
        "schema": "pointer_gpf.v2.flow_lock.v1",
        "pid": pid,
        "token": current_token,
        "project_root": str(project_root.resolve()),
        "recovered_stale_lock": recovered_stale_lock,
    }
    if stale_lock is not None:
        payload["stale_lock"] = stale_lock
    lock_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def verify_teardown(
    project_root: Path,
    *,
    read_runtime_gate: Callable[[Path], dict[str, Any]],
    list_project_processes: Callable[[Path], list[dict[str, Any]]],
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    timeout_ms: int = 10000,
    stable_ms: int = 500,
) -> dict[str, Any]:
    deadline = monotonic() + max(1, timeout_ms) / 1000.0
    last_gate = read_runtime_gate(project_root)
    last_processes = list_project_processes(project_root)
    stopped_since: float | None = None
    last_now = monotonic()
    while monotonic() < deadline:
        now = monotonic()
        last_now = now
        last_gate = read_runtime_gate(project_root)
        last_processes = list_project_processes(project_root)
        play_stopped = not bool(last_gate.get("runtime_gate_passed", False))
        process_count_ok = len(last_processes) == 0
        if play_stopped and process_count_ok:
            if stopped_since is None:
                stopped_since = now
            stable_stop_ms = int(max(0.0, now - stopped_since) * 1000)
        else:
            stopped_since = None
            stable_stop_ms = 0
        if play_stopped and process_count_ok and stable_stop_ms >= stable_ms:
            return {
                "status": "verified",
                "runtime_gate": last_gate,
                "project_process_count": len(last_processes),
                "project_processes": last_processes,
                "stable_stop_ms": stable_stop_ms,
                "required_stable_stop_ms": stable_ms,
            }
        sleep(0.1)
    return {
        "status": "failed",
        "runtime_gate": last_gate,
        "project_process_count": len(last_processes),
        "project_processes": last_processes,
        "stable_stop_ms": int(max(0.0, (last_now - stopped_since) * 1000)) if stopped_since is not None else 0,
        "required_stable_stop_ms": stable_ms,
    }
