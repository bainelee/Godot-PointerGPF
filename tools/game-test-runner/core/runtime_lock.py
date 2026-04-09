from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


def runtime_lock_path(project_root: Path) -> Path:
    return project_root / "artifacts" / "test-runs" / ".runtime_lock.json"


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            probe = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
        except Exception:
            return True
        out = str(probe.stdout or "").strip()
        if not out:
            return False
        lowered = out.lower()
        if lowered.startswith("info:") or "no tasks are running" in lowered:
            return False
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def load_runtime_lock(project_root: Path) -> dict[str, Any]:
    path = runtime_lock_path(project_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def acquire_runtime_lock(
    *,
    project_root: Path,
    pid: int,
    run_id: str,
    owner: str,
    allow_parallel: bool = False,
) -> dict[str, Any]:
    if allow_parallel:
        return {"locked": False, "allow_parallel": True}
    path = runtime_lock_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_runtime_lock(project_root)
    existing_pid = int(current.get("pid", 0) or 0)
    if existing_pid > 0 and existing_pid != pid and is_pid_running(existing_pid):
        raise RuntimeError(
            json.dumps(
                {
                    "code": "TEST_RUNTIME_ACTIVE",
                    "pid": existing_pid,
                    "run_id": str(current.get("run_id", "")),
                    "owner": str(current.get("owner", "")),
                },
                ensure_ascii=False,
            )
        )
    payload = {
        "pid": int(pid),
        "run_id": str(run_id),
        "owner": str(owner),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"locked": True, "pid": int(pid), "run_id": str(run_id), "owner": str(owner)}


def release_runtime_lock(project_root: Path, pid: int) -> None:
    path = runtime_lock_path(project_root)
    if not path.exists():
        return
    payload = load_runtime_lock(project_root)
    lock_pid = int(payload.get("pid", 0) or 0)
    if lock_pid > 0 and lock_pid != int(pid):
        return
    try:
        path.unlink()
    except OSError:
        pass
