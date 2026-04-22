from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .test_project_bug_round import round_dir, restore_bug_round_baseline


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _timestamp(*, now_fn: Callable[[], datetime] = datetime.now) -> str:
    return now_fn().isoformat(timespec="seconds")


def _restore_result_path(project_root: Path, round_id: str) -> Path:
    return (round_dir(project_root, round_id) / "restore_result.json").resolve()


def _default_restore_verification_command(project_root: Path) -> list[str]:
    repo_root = Path(__file__).resolve().parents[2]
    return [
        sys.executable,
        str(repo_root / "scripts" / "verify-v2-regression.py"),
        "--project-root",
        str(project_root.resolve()),
    ]


def restore_test_project_bug_round(
    project_root: Path,
    args: Any,
    *,
    build_command: Callable[[Path], list[str]] = _default_restore_verification_command,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    now_fn: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    round_id = str(getattr(args, "round_id", "") or "").strip()
    if not round_id:
        raise ValueError("--round-id is required for restore_test_project_bug_round")
    restore_files_result = restore_bug_round_baseline(project_root, round_id, now_fn=now_fn)
    command = build_command(project_root)
    proc = subprocess_run(command, cwd=str(Path(__file__).resolve().parents[2]), capture_output=True, text=True, timeout=900)
    stdout = str(proc.stdout or "").strip()
    stderr = str(proc.stderr or "").strip()
    parsed: dict[str, Any] = {}
    if stdout:
        try:
            maybe = json.loads(stdout)
            if isinstance(maybe, dict):
                parsed = maybe
        except json.JSONDecodeError:
            parsed = {}
    status = "restored_and_verified" if proc.returncode == 0 and bool(parsed.get("ok")) else "restore_verification_failed"
    payload = {
        "schema": "pointer_gpf.v2.test_project_bug_restore.v1",
        "project_root": str(project_root.resolve()),
        "round_id": round_id,
        "status": status,
        "restored_at": _timestamp(now_fn=now_fn),
        "restore_files_result": restore_files_result,
        "verification_command": command,
        "verification_returncode": proc.returncode,
        "verification_stdout": stdout,
        "verification_stderr": stderr,
        "verification_result": parsed,
    }
    payload["artifact_file"] = str(_write_json(_restore_result_path(project_root, round_id), payload))
    return payload
