from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


def create_round_id(*, now_fn: Callable[[], datetime] = datetime.now) -> str:
    return now_fn().strftime("%Y%m%d-%H%M%S-%f")


def bug_rounds_root(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp" / "bug_dev_rounds").resolve()


def round_dir(project_root: Path, round_id: str) -> Path:
    return (bug_rounds_root(project_root) / str(round_id).strip()).resolve()


def baseline_manifest_path(project_root: Path, round_id: str) -> Path:
    return (round_dir(project_root, round_id) / "baseline_manifest.json").resolve()


def bug_injection_plan_path(project_root: Path, round_id: str) -> Path:
    return (round_dir(project_root, round_id) / "bug_injection_plan.json").resolve()


def restore_plan_path(project_root: Path, round_id: str) -> Path:
    return (round_dir(project_root, round_id) / "restore_plan.json").resolve()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _timestamp(*, now_fn: Callable[[], datetime] = datetime.now) -> str:
    return now_fn().isoformat(timespec="seconds")


def _normalize_project_relative_path(project_root: Path, raw_path: str) -> str:
    cleaned = str(raw_path or "").strip()
    if not cleaned:
        raise ValueError("file path cannot be empty")
    if cleaned.startswith("res://"):
        relative = cleaned[len("res://") :]
    else:
        candidate = Path(cleaned)
        if candidate.is_absolute():
            resolved_candidate = candidate.resolve()
            resolved_project_root = project_root.resolve()
            try:
                relative = str(resolved_candidate.relative_to(resolved_project_root))
            except ValueError as exc:
                raise ValueError(f"file path must stay inside the target project: {cleaned}") from exc
        else:
            relative = cleaned
    normalized = Path(relative.replace("\\", "/")).as_posix().lstrip("/")
    if not normalized:
        raise ValueError(f"invalid project-relative file path: {raw_path}")
    return normalized


def project_relative_to_res_path(project_relative_path: str) -> str:
    normalized = Path(str(project_relative_path or "").replace("\\", "/")).as_posix().lstrip("/")
    return f"res://{normalized}" if normalized else ""


def project_relative_to_absolute_path(project_root: Path, project_relative_path: str) -> Path:
    normalized = _normalize_project_relative_path(project_root, project_relative_path)
    return (project_root / Path(normalized)).resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _baseline_copy_path(project_root: Path, round_id: str, project_relative_path: str) -> Path:
    normalized = _normalize_project_relative_path(project_root, project_relative_path)
    return (round_dir(project_root, round_id) / "baseline_files" / Path(normalized)).resolve()


def parse_files_to_record(project_root: Path, args: Any, *, extra_files: list[str] | None = None) -> list[str]:
    files: list[str] = []

    def add(raw_path: str) -> None:
        cleaned = str(raw_path or "").strip()
        if not cleaned:
            return
        normalized = _normalize_project_relative_path(project_root, cleaned)
        if normalized not in files:
            files.append(normalized)

    raw_files = str(getattr(args, "files_to_record", "") or "").strip()
    if raw_files:
        for part in raw_files.split("|"):
            add(part)
    add(str(getattr(args, "location_script", "") or "").strip())
    add(str(getattr(args, "location_scene", "") or "").strip())
    if extra_files:
        for item in extra_files:
            add(item)
    return files


def _bug_context_from_args(args: Any) -> dict[str, Any]:
    return {
        "bug_kind": str(getattr(args, "bug_kind", "") or "").strip(),
        "bug_summary": str(getattr(args, "bug_summary", "") or "").strip(),
        "bug_report": str(getattr(args, "bug_report", "") or "").strip(),
        "expected_behavior": str(getattr(args, "expected_behavior", "") or "").strip(),
        "steps_to_trigger": str(getattr(args, "steps_to_trigger", "") or "").strip(),
        "location_scene": str(getattr(args, "location_scene", "") or "").strip(),
        "location_node": str(getattr(args, "location_node", "") or "").strip(),
        "location_script": str(getattr(args, "location_script", "") or "").strip(),
    }


def record_bug_round_baseline(
    project_root: Path,
    round_id: str,
    files_to_record: list[str],
    *,
    bug_context: dict[str, Any] | None = None,
    planned_bugs: list[dict[str, Any]] | None = None,
    now_fn: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    cleaned_round_id = str(round_id or "").strip()
    if not cleaned_round_id:
        raise ValueError("round_id is required")
    normalized_files = [_normalize_project_relative_path(project_root, item) for item in files_to_record if str(item).strip()]
    if not normalized_files:
        raise ValueError("at least one project file must be recorded before bug injection")

    manifest_file = baseline_manifest_path(project_root, cleaned_round_id)
    existing_manifest = _load_json(manifest_file)
    existing_entries = existing_manifest.get("files", [])
    if not isinstance(existing_entries, list):
        existing_entries = []
    recorded_by_relative: dict[str, dict[str, Any]] = {}
    for item in existing_entries:
        if not isinstance(item, dict):
            continue
        key = str(item.get("project_relative_path", "")).strip()
        if key:
            recorded_by_relative[key] = item

    for project_relative_path in normalized_files:
        absolute_path = project_relative_to_absolute_path(project_root, project_relative_path)
        if not absolute_path.is_file():
            raise ValueError(f"recorded baseline file does not exist: {project_relative_to_res_path(project_relative_path)}")
        if project_relative_path in recorded_by_relative:
            continue
        baseline_copy = _baseline_copy_path(project_root, cleaned_round_id, project_relative_path)
        baseline_copy.parent.mkdir(parents=True, exist_ok=True)
        baseline_copy.write_bytes(absolute_path.read_bytes())
        recorded_by_relative[project_relative_path] = {
            "project_relative_path": project_relative_path,
            "res_path": project_relative_to_res_path(project_relative_path),
            "absolute_path": str(absolute_path),
            "baseline_copy_relative": str(baseline_copy.relative_to(round_dir(project_root, cleaned_round_id))).replace("\\", "/"),
            "baseline_copy_absolute": str(baseline_copy),
            "size_bytes": absolute_path.stat().st_size,
            "sha256": _sha256(absolute_path),
        }

    manifest_payload = {
        "schema": "pointer_gpf.v2.test_project_bug_round_baseline.v1",
        "round_id": cleaned_round_id,
        "project_root": str(project_root.resolve()),
        "round_dir": str(round_dir(project_root, cleaned_round_id)),
        "created_at": existing_manifest.get("created_at") or _timestamp(now_fn=now_fn),
        "updated_at": _timestamp(now_fn=now_fn),
        "bug_context": bug_context or existing_manifest.get("bug_context", {}),
        "files": [recorded_by_relative[key] for key in sorted(recorded_by_relative)],
    }
    manifest_path = _write_json(manifest_file, manifest_payload)

    planned_bug_entries = planned_bugs if isinstance(planned_bugs, list) else []
    plan_file = bug_injection_plan_path(project_root, cleaned_round_id)
    existing_plan = _load_json(plan_file)
    existing_bug_entries = existing_plan.get("bugs", [])
    if not isinstance(existing_bug_entries, list):
        existing_bug_entries = []
    plan_payload = {
        "schema": "pointer_gpf.v2.test_project_bug_injection_plan.v1",
        "round_id": cleaned_round_id,
        "project_root": str(project_root.resolve()),
        "created_at": existing_plan.get("created_at") or _timestamp(now_fn=now_fn),
        "updated_at": _timestamp(now_fn=now_fn),
        "bugs": existing_bug_entries or planned_bug_entries,
    }
    plan_path = _write_json(plan_file, plan_payload)

    restore_actions = [
        {
            "project_relative_path": item["project_relative_path"],
            "res_path": item["res_path"],
            "baseline_copy_relative": item["baseline_copy_relative"],
            "baseline_copy_absolute": item["baseline_copy_absolute"],
        }
        for item in manifest_payload["files"]
    ]
    restore_payload = {
        "schema": "pointer_gpf.v2.test_project_bug_restore_plan.v1",
        "round_id": cleaned_round_id,
        "project_root": str(project_root.resolve()),
        "created_at": existing_manifest.get("created_at") or _timestamp(now_fn=now_fn),
        "updated_at": _timestamp(now_fn=now_fn),
        "restore_actions": restore_actions,
    }
    restore_path = _write_json(restore_plan_path(project_root, cleaned_round_id), restore_payload)
    return {
        "schema": "pointer_gpf.v2.test_project_bug_round_record.v1",
        "project_root": str(project_root.resolve()),
        "round_id": cleaned_round_id,
        "round_dir": str(round_dir(project_root, cleaned_round_id)),
        "status": "baseline_recorded",
        "files_recorded": restore_actions,
        "baseline_manifest_file": str(manifest_path),
        "bug_injection_plan_file": str(plan_path),
        "restore_plan_file": str(restore_path),
    }


def update_bug_injection_plan(
    project_root: Path,
    round_id: str,
    bug_record: dict[str, Any],
    *,
    now_fn: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    cleaned_round_id = str(round_id or "").strip()
    if not cleaned_round_id:
        raise ValueError("round_id is required")
    if not isinstance(bug_record, dict):
        raise ValueError("bug_record must be a dictionary")
    bug_id = str(bug_record.get("bug_id", "")).strip()
    if not bug_id:
        raise ValueError("bug_record.bug_id is required")
    plan_file = bug_injection_plan_path(project_root, cleaned_round_id)
    plan_payload = _load_json(plan_file)
    bugs = plan_payload.get("bugs", [])
    if not isinstance(bugs, list):
        bugs = []
    updated = False
    merged_bugs: list[dict[str, Any]] = []
    for item in bugs:
        if isinstance(item, dict) and str(item.get("bug_id", "")).strip() == bug_id:
            merged = dict(item)
            merged.update(bug_record)
            merged_bugs.append(merged)
            updated = True
        else:
            merged_bugs.append(item if isinstance(item, dict) else {})
    if not updated:
        merged_bugs.append(bug_record)
    payload = {
        "schema": "pointer_gpf.v2.test_project_bug_injection_plan.v1",
        "round_id": cleaned_round_id,
        "project_root": str(project_root.resolve()),
        "created_at": plan_payload.get("created_at") or _timestamp(now_fn=now_fn),
        "updated_at": _timestamp(now_fn=now_fn),
        "bugs": merged_bugs,
    }
    _write_json(plan_file, payload)
    return payload


def restore_bug_round_baseline(
    project_root: Path,
    round_id: str,
    *,
    now_fn: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    cleaned_round_id = str(round_id or "").strip()
    restore_payload = _load_json(restore_plan_path(project_root, cleaned_round_id))
    actions = restore_payload.get("restore_actions", [])
    if not isinstance(actions, list) or not actions:
        raise ValueError(f"no restore plan exists for round {cleaned_round_id}")

    restored_files: list[dict[str, str]] = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        project_relative_path = _normalize_project_relative_path(project_root, str(item.get("project_relative_path", "")).strip())
        baseline_copy = round_dir(project_root, cleaned_round_id) / str(item.get("baseline_copy_relative", "")).replace("/", "\\")
        target_path = project_relative_to_absolute_path(project_root, project_relative_path)
        if not baseline_copy.is_file():
            raise ValueError(f"baseline copy is missing for restore: {baseline_copy}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(baseline_copy.read_bytes())
        restored_files.append(
            {
                "project_relative_path": project_relative_path,
                "res_path": project_relative_to_res_path(project_relative_path),
                "absolute_path": str(target_path),
            }
        )

    result = {
        "schema": "pointer_gpf.v2.test_project_bug_restore_files.v1",
        "round_id": cleaned_round_id,
        "project_root": str(project_root.resolve()),
        "status": "restored",
        "restored_at": _timestamp(now_fn=now_fn),
        "restored_files": restored_files,
        "restore_plan_file": str(restore_plan_path(project_root, cleaned_round_id)),
        "baseline_manifest_file": str(baseline_manifest_path(project_root, cleaned_round_id)),
    }
    _write_json(round_dir(project_root, cleaned_round_id) / "restore_files_result.json", result)
    return result


def start_test_project_bug_round(
    project_root: Path,
    args: Any,
    *,
    create_round_id_fn: Callable[[], str] = create_round_id,
    now_fn: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    round_id = str(getattr(args, "round_id", "") or "").strip() or create_round_id_fn()
    files_to_record = parse_files_to_record(project_root, args)
    if not files_to_record:
        raise ValueError("--files-to-record or at least one location hint file is required")
    payload = record_bug_round_baseline(
        project_root,
        round_id,
        files_to_record,
        bug_context=_bug_context_from_args(args),
        planned_bugs=[],
        now_fn=now_fn,
    )
    payload["schema"] = "pointer_gpf.v2.test_project_bug_round_start.v1"
    payload["status"] = "round_started"
    return payload
