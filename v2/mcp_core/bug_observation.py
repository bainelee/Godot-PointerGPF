from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .basicflow_assets import BasicFlowAssetError, load_basicflow_assets
from .bug_assertions import define_bug_assertions
from .bug_fix_verification import bug_fix_verification_path
from .bug_repro_execution import load_repro_result, repro_result_path

_MAIN_SCENE_RE = re.compile(r'^run/main_scene="(?P<path>res://[^"]+)"$', re.MULTILINE)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _runtime_diagnostics_path(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp" / "runtime_diagnostics.json").resolve()


def _read_startup_scene(project_root: Path) -> str:
    project_file = project_root / "project.godot"
    if not project_file.is_file():
        return ""
    try:
        text = project_file.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = _MAIN_SCENE_RE.search(text)
    return str(match.group("path")).strip() if match else ""


def _basicflow_summary(project_root: Path) -> dict[str, Any]:
    try:
        assets = load_basicflow_assets(project_root)
    except BasicFlowAssetError:
        return {
            "exists": False,
            "flow_file": "",
            "step_count": 0,
            "related_files": [],
            "runtime_hints": [],
        }
    flow = assets.get("flow", {})
    meta = assets.get("meta", {})
    steps = flow.get("steps", []) if isinstance(flow, dict) else []
    hints: list[dict[str, str]] = []
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            hint = ""
            if isinstance(step.get("until"), dict):
                hint = str(step["until"].get("hint", "")).strip()
            if not hint:
                hint = str(step.get("hint", "")).strip()
            if not hint and isinstance(step.get("target"), dict):
                hint = str(step["target"].get("hint", "")).strip()
            if hint:
                hints.append(
                    {
                        "step_id": str(step.get("id", "")).strip(),
                        "action": str(step.get("action", "")).strip(),
                        "hint": hint,
                    }
                )
    related_files = meta.get("related_files", []) if isinstance(meta, dict) else []
    return {
        "exists": True,
        "flow_file": str((project_root / "pointer_gpf" / "basicflow.json").resolve()),
        "step_count": len(steps) if isinstance(steps, list) else 0,
        "related_files": [str(item).strip() for item in related_files if str(item).strip()][:8],
        "runtime_hints": hints[:10],
    }


def _runtime_diagnostics_summary(project_root: Path) -> dict[str, Any]:
    path = _runtime_diagnostics_path(project_root)
    payload = _read_json(path)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []
    summaries: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summaries.append(
            {
                "kind": str(item.get("kind", "")).strip(),
                "message": str(item.get("message", "")).strip(),
            }
        )
    severity = str(payload.get("severity", "")).strip()
    blocking = [
        item
        for item in summaries
        if item["kind"].lower() in {"engine_log_error", "bridge_error"}
        and "acknowledged" not in item["message"].lower()
    ]
    return {
        "exists": path.is_file(),
        "path": str(path),
        "severity": severity,
        "item_count": len(summaries),
        "blocking_count": len(blocking),
        "items": summaries[:5],
        "blocking_items": blocking[:3],
    }


def _latest_repro_summary(project_root: Path) -> dict[str, Any]:
    payload = load_repro_result(project_root)
    artifact_path = str(repro_result_path(project_root))
    if not payload:
        return {
            "exists": False,
            "status": "",
            "failed_phase": "",
            "next_action": "",
            "artifact_file": artifact_path,
        }
    raw_error = payload.get("raw_run_result", {}).get("error", {}) if isinstance(payload.get("raw_run_result", {}), dict) else {}
    details = raw_error.get("details", {}) if isinstance(raw_error, dict) else {}
    if not isinstance(details, dict):
        details = {}
    return {
        "exists": True,
        "status": str(payload.get("status", "")).strip(),
        "failed_phase": str(payload.get("failed_phase", "")).strip(),
        "next_action": str(payload.get("next_action", "")).strip(),
        "artifact_file": str(payload.get("artifact_file", "")).strip() or artifact_path,
        "step_id": str(details.get("step_id", "")).strip(),
        "blocking_point": str(payload.get("blocking_point", "")).strip(),
        "check_summary": payload.get("check_summary", {}) if isinstance(payload.get("check_summary", {}), dict) else {},
        "runtime_evidence_summary": payload.get("runtime_evidence_summary", {})
        if isinstance(payload.get("runtime_evidence_summary", {}), dict)
        else {},
    }


def _latest_fix_verification_summary(project_root: Path) -> dict[str, Any]:
    path = bug_fix_verification_path(project_root)
    payload = _read_json(path)
    if not payload:
        return {
            "exists": False,
            "status": "",
            "reason": "",
            "artifact_file": str(path),
        }
    return {
        "exists": True,
        "status": str(payload.get("status", "")).strip(),
        "reason": str(payload.get("reason", "")).strip(),
        "artifact_file": str(path),
        "round_id": str(payload.get("round_id", "")).strip(),
        "bug_id": str(payload.get("bug_id", "")).strip(),
    }


def _candidate_file_read_order(assertion_set: dict[str, Any], basicflow_summary: dict[str, Any]) -> list[str]:
    bug_analysis = assertion_set.get("bug_analysis", {})
    artifacts = bug_analysis.get("affected_artifacts", {}) if isinstance(bug_analysis, dict) else {}
    scripts = artifacts.get("scripts", []) if isinstance(artifacts, dict) else []
    scenes = artifacts.get("scenes", []) if isinstance(artifacts, dict) else []
    related_files = basicflow_summary.get("related_files", [])
    candidates: list[str] = []
    for group in (scripts, scenes, related_files):
        if not isinstance(group, list):
            continue
        for item in group:
            value = str(item).strip()
            if value and value not in candidates:
                candidates.append(value)
    return candidates[:10]


def observe_bug_context(project_root: Path, args: Any) -> dict[str, Any]:
    assertion_set = define_bug_assertions(project_root, args)
    bug_analysis = assertion_set.get("bug_analysis", {})
    bug_intake = bug_analysis.get("bug_intake", {}) if isinstance(bug_analysis, dict) else {}
    basicflow_summary = _basicflow_summary(project_root)
    runtime_summary = _runtime_diagnostics_summary(project_root)
    repro_summary = _latest_repro_summary(project_root)
    verification_summary = _latest_fix_verification_summary(project_root)
    return {
        "schema": "pointer_gpf.v2.bug_observation.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": assertion_set.get("bug_summary", ""),
        "startup_scene": _read_startup_scene(project_root),
        "bug_intake": bug_intake,
        "bug_analysis": bug_analysis,
        "assertion_set": assertion_set,
        "basicflow_summary": basicflow_summary,
        "runtime_diagnostics": runtime_summary,
        "latest_repro_result": repro_summary,
        "runtime_evidence_capabilities": {
            "schema": "pointer_gpf.v2.runtime_evidence_capabilities.v1",
            "actions": ["sample", "observe", "check"],
            "record_types": ["read_result", "sample_result", "event_observer_result", "comparison_result"],
            "status": "contract_defined_python_side",
        },
        "latest_runtime_evidence_summary": repro_summary.get("runtime_evidence_summary", {})
        if isinstance(repro_summary.get("runtime_evidence_summary", {}), dict)
        else {},
        "latest_fix_verification": verification_summary,
        "candidate_file_read_order": _candidate_file_read_order(assertion_set, basicflow_summary),
        "investigation_focus": list(bug_analysis.get("recommended_assertion_focus", []))[:5] if isinstance(bug_analysis, dict) else [],
    }
