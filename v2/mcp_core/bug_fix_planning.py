from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .bug_repro_execution import load_repro_result
from .test_project_bug_case import bug_case_request_metadata


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


def _suggest_fix_goals_from_evidence(repro_payload: dict[str, Any], observation: dict[str, Any]) -> list[str]:
    goals: list[str] = []
    check_summary = repro_payload.get("check_summary", {})
    failed_checks = check_summary.get("failed_checks", []) if isinstance(check_summary, dict) else []
    for failed in failed_checks:
        if not isinstance(failed, dict):
            continue
        assertion_id = str(failed.get("source_assertion_id", "")).strip()
        hint = str(failed.get("hint", "")).strip()
        if assertion_id == "target_scene_reached" or "node_exists:GameLevel" in hint:
            goals.append("restore the trigger-to-scene transition so the expected gameplay scene appears after the interaction")
        elif assertion_id == "interaction_target_hidden_after_success":
            goals.append("restore the post-trigger UI state so the original interaction target no longer remains visible after success")
        elif "GamePointerHud" in hint:
            goals.append("restore the gameplay HUD path so the expected HUD anchor exists after the scene transition")
        check_type = str(failed.get("check_type", "")).strip()
        evidence_ref = str(failed.get("evidence_ref", "")).strip()
        if evidence_ref and "changes_within_window" in check_type:
            goals.append(f"make the observed runtime value change during the evidence window {evidence_ref}")
        elif evidence_ref and "returns_to_baseline" in check_type:
            goals.append(f"make the observed runtime value return to baseline for evidence window {evidence_ref}")
        elif evidence_ref and "signal" in check_type:
            goals.append(f"make the expected runtime event occur during evidence window {evidence_ref}")
        elif evidence_ref:
            goals.append(f"repair the code path that failed evidence-backed check {evidence_ref}")

    runtime_evidence_summary = repro_payload.get("runtime_evidence_summary", {})
    if isinstance(runtime_evidence_summary, dict):
        failed_evidence_ids = runtime_evidence_summary.get("failed_evidence_ids", [])
        if isinstance(failed_evidence_ids, list):
            for evidence_id in failed_evidence_ids[:3]:
                cleaned = str(evidence_id).strip()
                if cleaned:
                    goals.append(f"inspect and repair the runtime path behind failed evidence {cleaned}")

    runtime_diagnostics = observation.get("runtime_diagnostics", {})
    if isinstance(runtime_diagnostics, dict) and int(runtime_diagnostics.get("blocking_count", 0) or 0) > 0:
        goals.append("inspect runtime diagnostics before editing unrelated files because engine or bridge errors are present")

    if not goals:
        goals.extend(_suggest_fix_goals(repro_payload))
    return _unique_non_empty(goals)[:5]


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


def _candidate_files_from_observation(project_root: Path, repro_payload: dict[str, Any], observation: dict[str, Any]) -> list[dict[str, str]]:
    base_candidates = _candidate_files(project_root, repro_payload)
    seen = {str(item.get("path", "")).strip() for item in base_candidates if isinstance(item, dict)}
    out = list(base_candidates)
    observation_files = observation.get("candidate_file_read_order", [])
    if not isinstance(observation_files, list):
        observation_files = []
    check_summary = repro_payload.get("check_summary", {})
    failed_checks = check_summary.get("failed_checks", []) if isinstance(check_summary, dict) else []
    failed_text = " ".join(
        [
            str(item.get("source_assertion_id", "")).strip()
            + " "
            + str(item.get("hint", "")).strip()
            + " "
            + str(item.get("check_type", "")).strip()
            + " "
            + str(item.get("evidence_ref", "")).strip()
            for item in failed_checks
            if isinstance(item, dict)
        ]
    ).lower()
    evidence_refs = [
        str(item.get("evidence_ref", "")).strip()
        for item in failed_checks
        if isinstance(item, dict) and str(item.get("evidence_ref", "")).strip()
    ]

    for path_text in observation_files:
        normalized = str(path_text).strip()
        if not normalized or normalized in seen:
            continue
        reason = "candidate file from bug observation"
        lowered = normalized.lower()
        if normalized.endswith(".gd"):
            if "gamepointerhud" in failed_text or "hud" in failed_text:
                if "hud" in lowered or "game_level" in lowered:
                    reason = "script is related to the failed HUD or gameplay-state checks"
            elif "target_scene_reached" in failed_text or "gamelevel" in failed_text:
                if "menu" in lowered or "main" in lowered or "game_level" in lowered:
                    reason = "script is related to the failed scene-transition checks"
            elif evidence_refs:
                reason = "script is a candidate from bug observation and the repro has failed runtime evidence refs: " + ", ".join(evidence_refs[:3])
        elif normalized.endswith(".tscn"):
            if "gamepointerhud" in failed_text or "hud" in failed_text:
                if "hud" in lowered or "game_level" in lowered:
                    reason = "scene is related to the failed HUD or gameplay-state checks"
            elif "target_scene_reached" in failed_text or "gamelevel" in failed_text:
                if "main" in lowered or "game_level" in lowered:
                    reason = "scene is related to the failed scene-transition checks"
            elif evidence_refs:
                reason = "scene is a candidate from bug observation and the repro has failed runtime evidence refs: " + ", ".join(evidence_refs[:3])
        absolute = project_root / normalized.replace("res://", "").replace("/", "\\") if normalized.startswith("res://") else None
        out.append(
            {
                "path": normalized,
                "absolute_path": str(absolute.resolve()) if absolute is not None else "",
                "reason": reason,
            }
        )
        seen.add(normalized)
        if len(out) >= 8:
            break
    return out


def _evidence_summary(repro_payload: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    check_summary = repro_payload.get("check_summary", {})
    if not isinstance(check_summary, dict):
        check_summary = {}
    runtime_diagnostics = observation.get("runtime_diagnostics", {})
    if not isinstance(runtime_diagnostics, dict):
        runtime_diagnostics = {}
    latest_repro = observation.get("latest_repro_result", {})
    if not isinstance(latest_repro, dict):
        latest_repro = {}
    runtime_evidence_summary = repro_payload.get("runtime_evidence_summary", {})
    if not isinstance(runtime_evidence_summary, dict):
        runtime_evidence_summary = {}
    runtime_evidence_records = repro_payload.get("runtime_evidence_records", [])
    if not isinstance(runtime_evidence_records, list):
        runtime_evidence_records = []
    compact_records: list[dict[str, Any]] = []
    for record in runtime_evidence_records[:5]:
        if not isinstance(record, dict):
            continue
        compact_records.append(
            {
                "evidence_id": str(record.get("evidence_id", "") or record.get("id", "")).strip(),
                "record_type": str(record.get("record_type", "") or record.get("type", "")).strip(),
                "status": str(record.get("status", "")).strip(),
                "target": record.get("target", {}) if isinstance(record.get("target", {}), dict) else {},
                "metric": record.get("metric", {}) if isinstance(record.get("metric", {}), dict) else {},
                "sample_count": len(record.get("samples", [])) if isinstance(record.get("samples", []), list) else 0,
                "event_count": len(record.get("events", [])) if isinstance(record.get("events", []), list) else 0,
            }
        )
    return {
        "repro_status": str(repro_payload.get("status", "")).strip(),
        "failed_phase": str(repro_payload.get("failed_phase", "")).strip(),
        "failed_check_ids": list(check_summary.get("failed_check_ids", []))[:5] if isinstance(check_summary.get("failed_check_ids", []), list) else [],
        "failed_checks": list(check_summary.get("failed_checks", []))[:5] if isinstance(check_summary.get("failed_checks", []), list) else [],
        "runtime_evidence_summary": runtime_evidence_summary,
        "runtime_evidence_records": compact_records,
        "blocking_runtime_items": list(runtime_diagnostics.get("blocking_items", []))[:3] if isinstance(runtime_diagnostics.get("blocking_items", []), list) else [],
        "latest_repro_step_id": str(latest_repro.get("step_id", "")).strip(),
    }


def _acceptance_checks(repro_payload: dict[str, Any]) -> list[dict[str, str]]:
    checks = repro_payload.get("executable_checks", [])
    if not isinstance(checks, list):
        checks = []
    out: list[dict[str, str]] = []
    for item in checks:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "check_id": str(item.get("check_id", "")).strip(),
                "assertion_id": str(item.get("source_assertion_id", "")).strip(),
                "action": str(item.get("action", "")).strip(),
                "hint": str(item.get("hint", "")).strip(),
                "check_type": str(item.get("check_type", "")).strip(),
                "evidence_ref": str(item.get("evidence_ref", "")).strip(),
                "predicate": item.get("predicate", {}) if isinstance(item.get("predicate", {}), dict) else {},
                "mapped_step_id": str(item.get("mapped_step_id", "")).strip(),
            }
        )
    return out[:8]


def _requested_bug_summary(args: Any) -> str:
    return str(getattr(args, "bug_summary", None) or getattr(args, "bug_report", "") or "").strip()


def _requested_bug_identity(args: Any) -> dict[str, str]:
    return {
        "scene": str(getattr(args, "location_scene", "") or "").strip(),
        "node": str(getattr(args, "location_node", "") or "").strip(),
        "script": str(getattr(args, "location_script", "") or "").strip(),
    }


def _artifact_matches_request(args: Any, repro_payload: dict[str, Any]) -> bool:
    requested_case = bug_case_request_metadata(args)
    requested_round_id = str(requested_case.get("round_id", "")).strip()
    requested_bug_id = str(requested_case.get("bug_id", "")).strip()
    if requested_round_id and str(repro_payload.get("round_id", "")).strip() not in {"", requested_round_id}:
        return False
    if requested_bug_id and str(repro_payload.get("bug_id", "")).strip() not in {"", requested_bug_id}:
        return False
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
    observe_bug_context_fn: Callable[[Path, Any], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    repro_payload = load_repro_result_fn(project_root)
    if not repro_payload:
        requested_case = bug_case_request_metadata(args)
        return {
            "schema": "pointer_gpf.v2.fix_plan.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": _requested_bug_summary(args),
            "round_id": str(requested_case.get("round_id", "")).strip(),
            "bug_id": str(requested_case.get("bug_id", "")).strip(),
            "bug_source": str(requested_case.get("bug_source", "pre_existing")).strip() or "pre_existing",
            "injected_bug_kind": str(requested_case.get("injected_bug_kind", "")).strip(),
            "bug_case_file": str(requested_case.get("bug_case_file", "")).strip(),
            "status": "fix_not_ready",
            "reason": "no persisted repro result exists yet for this project",
            "repro_status": "",
            "repro_run": {},
            "candidate_files": [],
            "fix_goals": [],
            "evidence_summary": {},
            "acceptance_checks": [],
            "next_action": "run_bug_repro_flow_first",
        }

    requested_bug_summary = _requested_bug_summary(args)
    artifact_bug_summary = str(repro_payload.get("bug_summary", "")).strip()
    if not _artifact_matches_request(args, repro_payload):
        return {
            "schema": "pointer_gpf.v2.fix_plan.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": artifact_bug_summary or requested_bug_summary,
            "round_id": str(repro_payload.get("round_id", "")).strip(),
            "bug_id": str(repro_payload.get("bug_id", "")).strip(),
            "bug_source": str(repro_payload.get("bug_source", "pre_existing")).strip() or "pre_existing",
            "injected_bug_kind": str(repro_payload.get("injected_bug_kind", "")).strip(),
            "bug_case_file": str(repro_payload.get("bug_case_file", "")).strip(),
            "status": "fix_not_ready",
            "reason": "the persisted repro artifact belongs to a different bug target than the current request",
            "repro_status": str(repro_payload.get("status", "")).strip(),
            "repro_run": repro_payload,
            "candidate_files": [],
            "fix_goals": [],
            "evidence_summary": {},
            "acceptance_checks": [],
            "next_action": "rerun_bug_repro_flow_for_this_bug",
        }

    repro_status = str(repro_payload.get("status", "")).strip()
    if repro_status != "bug_reproduced":
        return {
            "schema": "pointer_gpf.v2.fix_plan.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": artifact_bug_summary or requested_bug_summary,
            "round_id": str(repro_payload.get("round_id", "")).strip(),
            "bug_id": str(repro_payload.get("bug_id", "")).strip(),
            "bug_source": str(repro_payload.get("bug_source", "pre_existing")).strip() or "pre_existing",
            "injected_bug_kind": str(repro_payload.get("injected_bug_kind", "")).strip(),
            "bug_case_file": str(repro_payload.get("bug_case_file", "")).strip(),
            "status": "fix_not_ready",
            "reason": "a code fix should not be planned until a persisted repro artifact confirms bug_reproduced",
            "repro_status": repro_status,
            "repro_run": repro_payload,
            "candidate_files": [],
            "fix_goals": [],
            "evidence_summary": {},
            "acceptance_checks": [],
            "next_action": str(repro_payload.get("next_action", "refine_repro_flow")),
        }

    if observe_bug_context_fn is None:
        from .bug_observation import observe_bug_context

        observe_bug_context_fn = observe_bug_context
    observation = observe_bug_context_fn(project_root, args)

    return {
        "schema": "pointer_gpf.v2.fix_plan.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": artifact_bug_summary or requested_bug_summary,
        "round_id": str(repro_payload.get("round_id", "")).strip(),
        "bug_id": str(repro_payload.get("bug_id", "")).strip(),
        "bug_source": str(repro_payload.get("bug_source", "pre_existing")).strip() or "pre_existing",
        "injected_bug_kind": str(repro_payload.get("injected_bug_kind", "")).strip(),
        "bug_case_file": str(repro_payload.get("bug_case_file", "")).strip(),
        "status": "fix_ready",
        "reason": "the persisted repro artifact confirms bug_reproduced, so code-level fix planning can start",
        "repro_status": repro_status,
        "repro_run": repro_payload,
        "observation": observation,
        "evidence_summary": _evidence_summary(repro_payload, observation),
        "candidate_files": _candidate_files_from_observation(project_root, repro_payload, observation),
        "fix_goals": _suggest_fix_goals_from_evidence(repro_payload, observation),
        "acceptance_checks": _acceptance_checks(repro_payload),
        "next_action": "inspect_candidate_files_and_edit_code",
    }
