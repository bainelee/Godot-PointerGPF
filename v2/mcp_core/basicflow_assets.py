from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .flow_runner import FlowContractError, load_flow


class BasicFlowAssetError(ValueError):
    pass


@dataclass(slots=True)
class BasicFlowPaths:
    flow_file: Path
    meta_file: Path


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def basicflow_paths(project_root: Path) -> BasicFlowPaths:
    base_dir = (project_root / "pointer_gpf").resolve()
    return BasicFlowPaths(
        flow_file=base_dir / "basicflow.json",
        meta_file=base_dir / "basicflow.meta.json",
    )


def basicflow_exists(project_root: Path) -> bool:
    paths = basicflow_paths(project_root)
    return paths.flow_file.is_file() and paths.meta_file.is_file()


def compute_project_file_summary(project_root: Path) -> dict[str, int]:
    total_file_count = 0
    script_count = 0
    scene_count = 0
    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        try:
            relative_parts = path.relative_to(project_root).parts
        except ValueError:
            relative_parts = ()
        if relative_parts[:1] == ("pointer_gpf",):
            continue
        total_file_count += 1
        suffix = path.suffix.lower()
        if suffix in {".gd", ".cs"}:
            script_count += 1
        if suffix == ".tscn":
            scene_count += 1
    return {
        "total_file_count": total_file_count,
        "script_count": script_count,
        "scene_count": scene_count,
    }


def validate_basicflow_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BasicFlowAssetError("basicflow metadata must be an object")

    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        raise BasicFlowAssetError("basicflow metadata field 'generated_at' must be a non-empty string")

    generation_summary = payload.get("generation_summary")
    if not isinstance(generation_summary, str) or not generation_summary.strip():
        raise BasicFlowAssetError("basicflow metadata field 'generation_summary' must be a non-empty string")

    related_files = payload.get("related_files")
    if not isinstance(related_files, list) or any(not isinstance(item, str) or not item.strip() for item in related_files):
        raise BasicFlowAssetError("basicflow metadata field 'related_files' must be a list of non-empty strings")

    project_file_summary = payload.get("project_file_summary")
    if not isinstance(project_file_summary, dict):
        raise BasicFlowAssetError("basicflow metadata field 'project_file_summary' must be an object")
    for key in ("total_file_count", "script_count", "scene_count"):
        value = project_file_summary.get(key)
        if not isinstance(value, int) or value < 0:
            raise BasicFlowAssetError(
                f"basicflow metadata project_file_summary field {key!r} must be a non-negative integer"
            )

    last_successful_run_at = payload.get("last_successful_run_at")
    if last_successful_run_at is not None and (
        not isinstance(last_successful_run_at, str) or not last_successful_run_at.strip()
    ):
        raise BasicFlowAssetError(
            "basicflow metadata field 'last_successful_run_at' must be null or a non-empty string"
        )

    return {
        "generated_at": generated_at,
        "generation_summary": generation_summary,
        "related_files": list(related_files),
        "project_file_summary": {
            "total_file_count": int(project_file_summary["total_file_count"]),
            "script_count": int(project_file_summary["script_count"]),
            "scene_count": int(project_file_summary["scene_count"]),
        },
        "last_successful_run_at": last_successful_run_at,
    }


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise BasicFlowAssetError(f"missing basicflow asset file: {path}") from exc
    except OSError as exc:
        raise BasicFlowAssetError(f"could not read basicflow asset file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BasicFlowAssetError(f"invalid JSON in basicflow asset file: {path}") from exc
    if not isinstance(payload, dict):
        raise BasicFlowAssetError(f"basicflow asset file must contain an object: {path}")
    return payload


def load_basicflow_assets(project_root: Path) -> dict[str, Any]:
    paths = basicflow_paths(project_root)
    flow_payload = _read_json_file(paths.flow_file)
    try:
        flow_payload = load_flow(paths.flow_file)
    except FlowContractError as exc:
        raise BasicFlowAssetError(f"invalid basicflow flow file: {exc}") from exc
    metadata = validate_basicflow_metadata(_read_json_file(paths.meta_file))
    return {
        "flow": flow_payload,
        "meta": metadata,
        "paths": {
            "flow_file": str(paths.flow_file),
            "meta_file": str(paths.meta_file),
        },
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def save_basicflow_assets(project_root: Path, flow_payload: dict[str, Any], metadata: dict[str, Any]) -> BasicFlowPaths:
    paths = basicflow_paths(project_root)
    if not isinstance(flow_payload, dict):
        raise BasicFlowAssetError("basicflow flow payload must be an object")
    validated_meta = validate_basicflow_metadata(metadata)
    paths.flow_file.parent.mkdir(parents=True, exist_ok=True)
    temp_flow = paths.flow_file.with_suffix(paths.flow_file.suffix + ".tmp")
    temp_flow.write_text(json.dumps(flow_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        load_flow(temp_flow)
    except FlowContractError as exc:
        temp_flow.unlink(missing_ok=True)
        raise BasicFlowAssetError(f"invalid basicflow flow file: {exc}") from exc
    temp_flow.replace(paths.flow_file)

    _write_json_atomic(paths.meta_file, validated_meta)
    return paths


def build_basicflow_metadata(
    *,
    generation_summary: str,
    related_files: list[str],
    project_file_summary: dict[str, int],
    generated_at: str | None = None,
    last_successful_run_at: str | None = None,
) -> dict[str, Any]:
    return validate_basicflow_metadata(
        {
            "generated_at": generated_at or _utc_iso(),
            "generation_summary": generation_summary,
            "related_files": related_files,
            "project_file_summary": project_file_summary,
            "last_successful_run_at": last_successful_run_at,
        }
    )


def mark_basicflow_run_success(project_root: Path, *, success_at: str | None = None) -> dict[str, Any]:
    assets = load_basicflow_assets(project_root)
    updated_meta = dict(assets["meta"])
    updated_meta["last_successful_run_at"] = success_at or _utc_iso()
    _write_json_atomic(basicflow_paths(project_root).meta_file, validate_basicflow_metadata(updated_meta))
    return updated_meta
