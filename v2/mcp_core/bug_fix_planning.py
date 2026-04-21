from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .bug_repro_execution import load_repro_result


def _unique_non_empty(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        cleaned = str(item or "").strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def _suggest_fix_goals(repro_payload: dict[str, Any]) -> list[str]:
    analysis = repro_payload.get("repro_flow_plan", {}).get("assertion_set", {}).get("bug_analysis", {})
    causes = analysis.get("suspected_causes", [])
    goals: list[str] = []
    for cause in causes:
        if not isinstance(cause, dict):
            continue
        kind = str(cause.get("kind", "")).strip()
        if kind == "button_signal_or_callback_broken":
            goals.append("verify the UI signal path and callback binding for the trigger interaction")
        elif kind == "scene_transition_not_triggered":
            goals.append("verify that the expected scene transition is invoked and reaches the target scene")
        elif kind == "script_path_should_be_inspected":
            goals.append("inspect the identified scripts for logic gaps around the bug trigger and expected state")
    if not goals:
        goals.append("inspect the affected runtime path and narrow the root cause before editing code")
    return _unique_non_empty(goals)[:4]


def _candidate_files(project_root: Path, repro_payload: dict[str, Any]) -> list[dict[str, str]]:
    analysis = repro_payload.get("repro_flow_plan", {}).get("assertion_set", {}).get("bug_analysis", {})
    intake = analysis.get("bug_intake", {})
    location_hint = intake.get("location_hint", {})
    scripts = analysis.get("affected_artifacts", {}).get("scripts", [])
    scenes = analysis.get("affected_artifacts", {}).get("scenes", [])
    files: list[dict[str, str]] = []

    def add(path_text: str, reason: str) -> None:
        normalized = str(path_text or "").strip()
        if not normalized:
            return
        for existing in files:
            if existing["path"] == normalized:
                return
        files.append({"path": normalized, "reason": reason})

    add(str(location_hint.get("script", "")).strip(), "bug intake location script")
    for script in scripts:
        add(script, "affected script from bug analysis")
    for scene in scenes:
        add(scene, "affected scene from bug analysis")

    out: list[dict[str, str]] = []
    for item in files[:6]:
        path_text = item["path"]
        absolute = project_root / path_text.replace("res://", "").replace("/", "\\") if path_text.startswith("res://") else None
        out.append(
            {
                "path": path_text,
                "absolute_path": str(absolute.resolve()) if absolute is not None else "",
                "reason": item["reason"],
            }
        )
    return out


def _requested_bug_summary(args: Any) -> str:
    return str(getattr(args, "bug_summary", None) or getattr(args, "bug_report", "") or "").strip()


def _requested_bug_identity(args: Any) -> dict[str, str]:
    return {
        "scene": str(getattr(args, "location_scene", "") or "").strip(),
        "node": str(getattr(args, "location_node", "") or "").strip(),
        "script": str(getattr(args, "location_script", "") or "").strip(),
    }


def _artifact_matches_request(args: Any, repro_payload: dict[str, Any]) -> bool:
    requested = _requested_bug_identity(args)
    artifact = repro_payload.get("bug_identity", {})
    if not isinstance(artifact, dict):
        return True
    for key, requested_value in requested.items():
        if not requested_value:
            continue
        artifact_value = str(artifact.get(key, "")).strip()
        if artifact_value and artifact_value != requested_value:
            return False
    return True


def plan_bug_fix(
    project_root: Path,
    args: Any,
    *,
    load_repro_result_fn: Callable[[Path], dict[str, Any]] = load_repro_result,
) -> dict[str, Any]:
    repro_payload = load_repro_result_fn(project_root)
    if not repro_payload:
        return {
            "schema": "pointer_gpf.v2.fix_plan.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": _requested_bug_summary(args),
            "status": "fix_not_ready",
            "reason": "no persisted repro result exists yet for this project",
            "repro_status": "",
            "repro_run": {},
            "candidate_files": [],
            "fix_goals": [],
            "next_action": "run_bug_repro_flow_first",
        }

    requested_bug_summary = _requested_bug_summary(args)
    artifact_bug_summary = str(repro_payload.get("bug_summary", "")).strip()
    if not _artifact_matches_request(args, repro_payload):
        return {
            "schema": "pointer_gpf.v2.fix_plan.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": artifact_bug_summary or requested_bug_summary,
            "status": "fix_not_ready",
            "reason": "the persisted repro artifact belongs to a different bug target than the current request",
            "repro_status": str(repro_payload.get("status", "")).strip(),
            "repro_run": repro_payload,
            "candidate_files": [],
            "fix_goals": [],
            "next_action": "rerun_bug_repro_flow_for_this_bug",
        }

    repro_status = str(repro_payload.get("status", "")).strip()
    if repro_status != "bug_reproduced":
        return {
            "schema": "pointer_gpf.v2.fix_plan.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": artifact_bug_summary or requested_bug_summary,
            "status": "fix_not_ready",
            "reason": "a code fix should not be planned until a persisted repro artifact confirms bug_reproduced",
            "repro_status": repro_status,
            "repro_run": repro_payload,
            "candidate_files": [],
            "fix_goals": [],
            "next_action": str(repro_payload.get("next_action", "refine_repro_flow")),
        }

    return {
        "schema": "pointer_gpf.v2.fix_plan.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": artifact_bug_summary or requested_bug_summary,
        "status": "fix_ready",
        "reason": "the persisted repro artifact confirms bug_reproduced, so code-level fix planning can start",
        "repro_status": repro_status,
        "repro_run": repro_payload,
        "candidate_files": _candidate_files(project_root, repro_payload),
        "fix_goals": _suggest_fix_goals(repro_payload),
        "next_action": "inspect_candidate_files_and_edit_code",
    }
