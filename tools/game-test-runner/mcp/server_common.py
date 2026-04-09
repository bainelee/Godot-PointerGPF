from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from artifact_service import load_json_dict
from server_errors import AppError

_CORE_DIR = Path(__file__).resolve().parents[1] / "core"
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))
from godot_executable_config import load_godot_executable_from_project_config  # noqa: E402


def load_report(run_root: Path) -> dict[str, Any]:
    return load_json_dict(run_root / "report.json")


def first_failure_reason(report_payload: dict[str, Any]) -> str:
    failures = report_payload.get("failures", [])
    if not isinstance(failures, list) or not failures:
        return ""
    first = failures[0] if isinstance(failures[0], dict) else {}
    reason = str(first.get("actual", "")).strip()
    category = str(first.get("category", "")).strip()
    if reason and category:
        return f"{category}: {reason}"
    return reason or category


def primary_failure_summary(report_payload: dict[str, Any]) -> dict[str, Any]:
    failures = report_payload.get("failures", [])
    if not isinstance(failures, list) or not failures:
        return {}
    first = failures[0] if isinstance(failures[0], dict) else {}
    step = str(first.get("stepId", ""))
    return {
        "step": step,
        "step_id": step,
        "category": str(first.get("category", "")),
        "expected": str(first.get("expected", "")),
        "actual": str(first.get("actual", "")),
        "artifacts": list(first.get("artifacts", []))
        if isinstance(first.get("artifacts", []), list)
        else [],
    }


def report_exit_codes(report_payload: dict[str, Any]) -> tuple[int | None, int | None]:
    if not isinstance(report_payload, dict):
        return None, None
    effective = report_payload.get("effective_exit_code")
    if effective is None:
        effective = report_payload.get("exitCode")
    process = report_payload.get("process_exit_code")
    try:
        effective = int(effective) if effective is not None else None
    except (TypeError, ValueError):
        effective = None
    try:
        process = int(process) if process is not None else None
    except (TypeError, ValueError):
        process = None
    return effective, process


def to_posix(value: str | Path) -> str:
    return str(value).replace("\\", "/")


def common_windows_godot_candidates() -> list[str]:
    out: list[str] = []
    roots = [
        os.environ.get("GODOT_HOME", ""),
        os.environ.get("ProgramFiles", ""),
        os.environ.get("ProgramFiles(x86)", ""),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
    ]
    for root in roots:
        root = str(root).strip()
        if not root:
            continue
        root_path = Path(root)
        if not root_path.exists():
            continue
        direct = [
            root_path / "Godot" / "godot.exe",
            root_path / "Godot" / "godot4.exe",
        ]
        for item in direct:
            if item.exists() and item.is_file():
                out.append(str(item))
        for pattern in ("Godot*.exe", "godot*.exe"):
            for item in root_path.glob(pattern):
                if item.is_file():
                    out.append(str(item))
            for item in (root_path / "Godot").glob(pattern):
                if item.is_file():
                    out.append(str(item))
    dedup: list[str] = []
    seen: set[str] = set()
    for item in out:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    return dedup


def _is_godot_request_placeholder(requested: str) -> bool:
    s = requested.strip().lower()
    if not s:
        return True
    return s in {"godot4", "godot", "godot4.exe", "godot.exe"}


def resolve_godot_bin(
    requested: str,
    strict: bool = False,
    allow_unresolved: bool = False,
    project_root: Path | str | None = None,
) -> tuple[str, dict[str, Any]]:
    requested = requested.strip()
    pr: Path | None = None
    if project_root is not None:
        p = Path(str(project_root)).resolve()
        pr = p if p.is_dir() else None

    candidates: list[str] = []
    if requested and not _is_godot_request_placeholder(requested):
        candidates.append(requested)
    env_bin = str(os.environ.get("GODOT_BIN", "")).strip()
    if env_bin:
        candidates.append(env_bin)
    cfg_bin = load_godot_executable_from_project_config(pr)
    if cfg_bin:
        candidates.append(cfg_bin)
    if requested:
        candidates.append(requested)
    candidates.extend(["godot4", "godot", "godot4.exe", "godot.exe"])
    candidates.extend(common_windows_godot_candidates())

    tried: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        if candidate in tried:
            continue
        tried.append(candidate)
        p = Path(candidate)
        if p.is_absolute() and p.exists() and p.is_file():
            return candidate, {"strategy": "absolute_path_exists", "requested": requested, "tried": tried}
        resolved = shutil.which(candidate)
        if resolved:
            return resolved, {"strategy": "which", "requested": requested, "tried": tried}

    if strict and requested:
        raise AppError("INVALID_ARGUMENT", f"strict_godot_bin=true but unresolved: {requested}", {"tried": tried})
    if not allow_unresolved:
        raise AppError(
            "MISSING_GODOT_BIN",
            (
                "Unable to resolve Godot executable. Set environment variable GODOT_BIN "
                "to a valid executable path, or ensure godot4/godot is available in PATH."
            ),
            {"requested": requested, "tried": tried},
        )
    if requested:
        return requested, {"strategy": "fallback_to_requested", "requested": requested, "tried": tried}
    return "godot4", {"strategy": "default", "requested": requested, "tried": tried}


def with_status_shape(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out["run_id"] = str(out.get("run_id", ""))
    out["status"] = str(out.get("status", "unknown"))
    out["current_step"] = str(out.get("current_step", ""))
    out["fix_loop_round"] = int(out.get("fix_loop_round", 0))
    out["approval_required"] = bool(out.get("approval_required", False))
    return out


def live_run_id(stem: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe = (stem or "flow").replace(" ", "_")
    return f"{ts}_{safe}_live"
