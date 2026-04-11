from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .basicflow_assets import BasicFlowAssetError, basicflow_exists, compute_project_file_summary, load_basicflow_assets


def _parse_utc_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_project_file(project_root: Path, raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/").strip()
    if normalized.startswith("res://"):
        normalized = normalized[len("res://") :]
    candidate = Path(normalized)
    if candidate.is_absolute():
        return candidate.resolve()
    return (project_root / candidate).resolve()


def _reason(code: str, message: str, *, priority: int, details: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "priority": priority,
    }
    if details:
        payload["details"] = details
    return payload


def detect_basicflow_staleness(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    if not basicflow_exists(project_root):
        return {
            "status": "missing",
            "is_stale": False,
            "reasons": [],
            "message": "basicflow assets do not exist yet",
        }

    try:
        assets = load_basicflow_assets(project_root)
    except BasicFlowAssetError as exc:
        return {
            "status": "missing",
            "is_stale": False,
            "reasons": [],
            "message": f"basicflow assets are unavailable: {exc}",
        }

    meta = assets["meta"]
    reasons: list[dict[str, Any]] = []
    generated_at = _parse_utc_iso(str(meta["generated_at"]))
    if generated_at is None:
        reasons.append(
            _reason(
                "BASICFLOW_GENERATED_AT_INVALID",
                "basicflow metadata generated_at is invalid, so freshness cannot be trusted",
                priority=1,
            )
        )

    related_files = meta.get("related_files", [])
    for raw_path in related_files:
        resolved = _resolve_project_file(project_root, str(raw_path))
        if not resolved.is_file():
            reasons.append(
                _reason(
                    "BASICFLOW_RELATED_FILE_MISSING",
                    f"basicflow related file is missing: {raw_path}",
                    priority=1,
                    details={"related_file": str(raw_path)},
                )
            )
            continue
        if generated_at is None:
            continue
        try:
            modified_at = datetime.fromtimestamp(resolved.stat().st_mtime, tz=timezone.utc)
        except OSError:
            reasons.append(
                _reason(
                    "BASICFLOW_RELATED_FILE_UNREADABLE",
                    f"basicflow related file could not be inspected: {raw_path}",
                    priority=1,
                    details={"related_file": str(raw_path)},
                )
            )
            continue
        if modified_at > generated_at:
            reasons.append(
                _reason(
                    "BASICFLOW_RELATED_FILE_CHANGED",
                    f"basicflow related file changed after generation: {raw_path}",
                    priority=1,
                    details={
                        "related_file": str(raw_path),
                        "generated_at": meta["generated_at"],
                        "modified_at": modified_at.isoformat(),
                    },
                )
            )

    current_summary = compute_project_file_summary(project_root)
    baseline_summary = meta.get("project_file_summary", {})
    deltas = {
        "total_file_count": current_summary["total_file_count"] - int(baseline_summary.get("total_file_count", 0)),
        "script_count": current_summary["script_count"] - int(baseline_summary.get("script_count", 0)),
        "scene_count": current_summary["scene_count"] - int(baseline_summary.get("scene_count", 0)),
    }
    if abs(deltas["script_count"]) >= 1 or abs(deltas["scene_count"]) >= 1 or abs(deltas["total_file_count"]) >= 3:
        reasons.append(
            _reason(
                "BASICFLOW_PROJECT_FILE_SUMMARY_CHANGED",
                "project file summary changed enough that the old basicflow may no longer be meaningful",
                priority=2,
                details={"baseline": baseline_summary, "current": current_summary, "delta": deltas},
            )
        )

    startup_scene = _read_startup_scene(project_root)
    if startup_scene:
        startup_scene_path = _resolve_project_file(project_root, startup_scene)
        if not startup_scene_path.is_file():
            reasons.append(
                _reason(
                    "BASICFLOW_STARTUP_SCENE_MISSING",
                    "current startup scene path from project.godot is missing",
                    priority=3,
                    details={"startup_scene": startup_scene},
                )
            )
        elif generated_at is not None:
            try:
                startup_modified_at = datetime.fromtimestamp(startup_scene_path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                startup_modified_at = None
            if startup_modified_at is not None and startup_modified_at > generated_at:
                reasons.append(
                    _reason(
                        "BASICFLOW_STARTUP_SCENE_CHANGED",
                        "current startup scene changed after basicflow generation",
                        priority=3,
                        details={
                            "startup_scene": startup_scene,
                            "generated_at": meta["generated_at"],
                            "modified_at": startup_modified_at.isoformat(),
                        },
                    )
                )

    if reasons:
        return {
            "status": "stale",
            "is_stale": True,
            "reasons": reasons,
            "message": "basicflow may be stale",
            "flow_summary": meta.get("generation_summary", ""),
        }
    return {
        "status": "fresh",
        "is_stale": False,
        "reasons": [],
        "message": "basicflow looks usable",
        "flow_summary": meta.get("generation_summary", ""),
    }


def analyze_basicflow_staleness(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    detection = detect_basicflow_staleness(project_root)
    if detection["status"] == "missing":
        return {
            "status": "missing",
            "message": detection["message"],
            "analysis_summary": "No project-local basicflow exists yet, so there is nothing to compare against the current project.",
            "recommended_next_step": "generate_basic_flow",
        }

    assets = load_basicflow_assets(project_root)
    meta = assets["meta"]
    current_summary = compute_project_file_summary(project_root)
    startup_scene = _read_startup_scene(project_root)
    assumptions = [
        "The current project-local basicflow assumes the project can launch and stay alive long enough for a baseline assertion.",
        "The current project-local basicflow assumes one visible click probe is still a meaningful minimal interaction.",
    ]
    if meta.get("related_files"):
        assumptions.append("The current project-local basicflow still relies on the recorded related files remaining compatible.")
    mismatch_summary = "No obvious mismatch detected between the current basicflow metadata and the current project snapshot."
    recommended_next_step = "run_basic_flow"
    if detection["status"] == "stale":
        mismatch_summary = "The recorded basicflow assumptions no longer fully match the current project snapshot."
        recommended_next_step = "regenerate_basicflow_or_run_with_allow_stale"
    return {
        "status": detection["status"],
        "message": detection["message"],
        "analysis_summary": mismatch_summary,
        "flow_summary": meta.get("generation_summary", ""),
        "assumptions": assumptions,
        "related_files": meta.get("related_files", []),
        "baseline_project_file_summary": meta.get("project_file_summary", {}),
        "current_project_file_summary": current_summary,
        "current_startup_scene": startup_scene,
        "reasons": detection.get("reasons", []),
        "recommended_next_step": recommended_next_step,
    }


def _read_startup_scene(project_root: Path) -> str:
    project_file = project_root / "project.godot"
    if not project_file.is_file():
        return ""
    current_section = ""
    try:
        lines = project_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip().lower()
            continue
        if current_section != "application":
            continue
        if not line.startswith("run/main_scene="):
            continue
        value = line.split("=", 1)[1].strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        return value
    return ""
