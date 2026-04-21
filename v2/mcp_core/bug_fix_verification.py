from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .bug_fix_application import apply_bug_fix
from .bug_repro_execution import rerun_bug_repro_flow


def bug_fix_regression_path(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp" / "last_bug_fix_regression.json").resolve()


def bug_fix_verification_path(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp" / "last_bug_fix_verification_summary.json").resolve()


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _default_regression_command(project_root: Path) -> list[str]:
    repo_root = Path(__file__).resolve().parents[2]
    return [
        sys.executable,
        str(repo_root / "scripts" / "verify-v2-regression.py"),
        "--project-root",
        str(project_root.resolve()),
    ]


def run_bug_fix_regression(
    project_root: Path,
    *,
    build_command: Callable[[Path], list[str]] = _default_regression_command,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    command = build_command(project_root)
    proc = subprocess_run(command, cwd=str(Path(__file__).resolve().parents[2]), capture_output=True, text=True, timeout=600)
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
    payload = {
        "schema": "pointer_gpf.v2.fix_regression.v1",
        "project_root": str(project_root.resolve()),
        "status": "passed" if proc.returncode == 0 and bool(parsed.get("ok")) else "failed",
        "command": command,
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "result": parsed,
        "summary": (
            "regression command passed"
            if proc.returncode == 0 and bool(parsed.get("ok"))
            else "regression command failed"
        ),
    }
    payload["artifact_file"] = str(_write_json(bug_fix_regression_path(project_root), payload))
    return payload


def verify_bug_fix(
    project_root: Path,
    args: Any,
    *,
    apply_bug_fix_fn: Callable[[Path, Any], dict[str, Any]] = apply_bug_fix,
    rerun_bug_repro_flow_fn: Callable[[Path, Any], dict[str, Any]] = rerun_bug_repro_flow,
    run_bug_fix_regression_fn: Callable[[Path], dict[str, Any]] = run_bug_fix_regression,
) -> dict[str, Any]:
    apply_payload = apply_bug_fix_fn(project_root, args)
    apply_status = str(apply_payload.get("status", "")).strip()
    if apply_status not in {"fix_applied", "already_aligned"}:
        payload = {
            "schema": "pointer_gpf.v2.fix_verification.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": str(apply_payload.get("bug_summary", "")).strip(),
            "status": "fix_verification_not_ready",
            "reason": "bug-fix verification requires a successful or already-aligned code change step",
            "apply_result": apply_payload,
            "rerun_result": {},
            "regression_result": {},
            "next_action": str(apply_payload.get("next_action", "inspect_candidate_files_and_edit_code")).strip(),
        }
        payload["artifact_file"] = str(_write_json(bug_fix_verification_path(project_root), payload))
        return payload

    rerun_payload = rerun_bug_repro_flow_fn(project_root, args)
    rerun_status = str(rerun_payload.get("status", "")).strip()
    if rerun_status != "bug_not_reproduced":
        payload = {
            "schema": "pointer_gpf.v2.fix_verification.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": str(apply_payload.get("bug_summary", "")).strip(),
            "status": "fix_verification_failed",
            "reason": "the bug-focused rerun still does not show a clean bug_not_reproduced result",
            "apply_result": apply_payload,
            "rerun_result": rerun_payload,
            "regression_result": {},
            "next_action": str(rerun_payload.get("next_action", "inspect_failure_before_fixing")).strip(),
        }
        payload["artifact_file"] = str(_write_json(bug_fix_verification_path(project_root), payload))
        return payload

    regression_payload = run_bug_fix_regression_fn(project_root)
    regression_status = str(regression_payload.get("status", "")).strip()
    payload = {
        "schema": "pointer_gpf.v2.fix_verification.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": str(apply_payload.get("bug_summary", "")).strip(),
        "status": "fix_verified" if regression_status == "passed" else "regression_failed",
        "reason": (
            "code change, bug-focused rerun, and regression all passed"
            if regression_status == "passed"
            else "the bug-focused rerun passed, but regression failed"
        ),
        "apply_result": apply_payload,
        "rerun_result": rerun_payload,
        "regression_result": regression_payload,
        "next_action": "" if regression_status == "passed" else "inspect_regression_failure",
    }
    payload["artifact_file"] = str(_write_json(bug_fix_verification_path(project_root), payload))
    return payload
