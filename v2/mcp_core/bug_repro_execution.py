from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .contracts import ERR_ENGINE_RUNTIME_STALLED, ERR_STEP_FAILED, ERR_TEARDOWN_VERIFICATION_FAILED, ERR_TIMEOUT
from .bug_repro_flow import plan_bug_repro_flow


def repro_result_path(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp" / "last_bug_repro_result.json").resolve()


def repro_verification_path(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp" / "last_bug_fix_verification.json").resolve()


def load_repro_result(project_root: Path) -> dict[str, Any]:
    target = repro_result_path(project_root)
    if not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_repro_result(project_root: Path, payload: dict[str, Any]) -> Path:
    target = repro_result_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _write_repro_verification(project_root: Path, payload: dict[str, Any]) -> Path:
    target = repro_verification_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _materialize_candidate_flow(project_root: Path, candidate_flow: dict[str, Any]) -> Path:
    target = (project_root / "pointer_gpf" / "tmp" / "planned_bug_repro_flow.json").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(candidate_flow, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _build_repro_gap(plan_payload: dict[str, Any], status: str) -> dict[str, Any]:
    coverage = plan_payload.get("assertion_coverage", [])
    if not isinstance(coverage, list):
        coverage = []
    unsupported = plan_payload.get("unsupported_assertions", [])
    if not isinstance(unsupported, list):
        unsupported = []
    base_covered = [
        item
        for item in coverage
        if isinstance(item, dict) and str(item.get("status", "")).strip() == "already_covered_by_base_flow"
    ]
    related_covered = [
        item
        for item in coverage
        if isinstance(item, dict) and str(item.get("status", "")).strip() == "covered_by_related_assertions"
    ]
    planned_covered = [
        item
        for item in coverage
        if isinstance(item, dict) and str(item.get("status", "")).strip() == "covered_by_planned_step"
    ]

    if status == "bug_not_reproduced":
        if unsupported:
            summary = "repro flow reached the current checkpoints, but some assertions still have no direct executable coverage"
            recommended_next_action = "add executable coverage for the unsupported assertions before treating this as a stable non-repro"
        elif related_covered:
            summary = "repro flow passed, but part of the bug expectation is still only indirectly covered by related assertions"
            recommended_next_action = "strengthen the repro trigger or add a more direct assertion for the state-change expectation"
        else:
            summary = "repro flow passed all currently covered post-trigger assertions without exposing the bug"
            recommended_next_action = "increase trigger specificity or introduce a stronger post-trigger assertion if the bug is still suspected"
    else:
        summary = ""
        recommended_next_action = ""

    return {
        "summary": summary,
        "base_flow_covered_assertions": [str(item.get("assertion_id", "")).strip() for item in base_covered],
        "planned_step_assertions": [str(item.get("assertion_id", "")).strip() for item in planned_covered],
        "indirectly_covered_assertions": [str(item.get("assertion_id", "")).strip() for item in related_covered],
        "unsupported_assertions": [str(item).strip() for item in unsupported],
        "recommended_next_action": recommended_next_action,
    }


def _build_refinement_plan(plan_payload: dict[str, Any], status: str, repro_gap: dict[str, Any]) -> dict[str, Any]:
    if status != "bug_not_reproduced":
        return {
            "status": "not_needed",
            "actions": [],
            "primary_action": "",
        }

    actions: list[dict[str, Any]] = []
    indirect = repro_gap.get("indirectly_covered_assertions", [])
    if isinstance(indirect, list):
        for assertion_id in indirect:
            assertion_name = str(assertion_id).strip()
            if assertion_name:
                actions.append(
                    {
                        "type": "add_direct_assertion",
                        "target_assertion": assertion_name,
                        "reason": "current repro only covers this expectation indirectly",
                    }
                )

    unsupported = repro_gap.get("unsupported_assertions", [])
    if isinstance(unsupported, list):
        for assertion_id in unsupported:
            assertion_name = str(assertion_id).strip()
            if assertion_name:
                actions.append(
                    {
                        "type": "make_assertion_executable",
                        "target_assertion": assertion_name,
                        "reason": "current repro plan has no direct runtime coverage for this assertion",
                    }
                )

    if actions:
        actions.append(
            {
                "type": "tighten_repro_trigger",
                "target_assertion": "",
                "reason": "the current flow reached all available checkpoints without exposing the bug",
            }
        )
        primary_action = str(actions[0].get("type", "")).strip()
        status_value = "refinement_needed"
    else:
        actions.append(
            {
                "type": "tighten_repro_trigger",
                "target_assertion": "",
                "reason": "the current flow passed all covered assertions, so stronger trigger specificity is needed",
            }
        )
        primary_action = "tighten_repro_trigger"
        status_value = "trigger_refinement_needed"

    return {
        "status": status_value,
        "actions": actions,
        "primary_action": primary_action,
    }


def _extract_error(raw_payload: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    error = raw_payload.get("error", {}) if isinstance(raw_payload, dict) else {}
    if not isinstance(error, dict):
        return "", "", {}
    details = error.get("details", {})
    if not isinstance(details, dict):
        details = {}
    return str(error.get("code", "")).strip(), str(error.get("message", "")).strip(), details


def _bug_identity(plan_payload: dict[str, Any]) -> dict[str, str]:
    intake = plan_payload.get("assertion_set", {}).get("bug_analysis", {}).get("bug_intake", {})
    if not isinstance(intake, dict):
        return {}
    location_hint = intake.get("location_hint", {})
    if not isinstance(location_hint, dict):
        location_hint = {}
    return {
        "scene": str(location_hint.get("scene", "")).strip(),
        "node": str(location_hint.get("node", "")).strip(),
        "script": str(location_hint.get("script", "")).strip(),
    }


def _classify_failed_phase(plan_payload: dict[str, Any], details: dict[str, Any]) -> str:
    contract = plan_payload.get("execution_contract", {})
    if not isinstance(contract, dict):
        contract = {}
    step_id = str(details.get("step_id", "")).strip()
    if not step_id:
        return "unknown"

    phase_map = {
        "setup": {str(item).strip() for item in contract.get("setup_step_ids", []) if str(item).strip()},
        "precondition": {str(item).strip() for item in contract.get("precondition_step_ids", []) if str(item).strip()},
        "trigger": {str(item).strip() for item in contract.get("trigger_step_ids", []) if str(item).strip()},
        "postcondition": {str(item).strip() for item in contract.get("postcondition_step_ids", []) if str(item).strip()},
        "close": {str(item).strip() for item in contract.get("close_step_ids", []) if str(item).strip()},
    }
    for phase, step_ids in phase_map.items():
        if step_id in step_ids:
            return phase
    return "unknown"


def _execute_repro_plan(
    *,
    project_root: Path,
    plan_payload: dict[str, Any],
    execution_mode_raw: str | None,
    run_basic_flow_tool: Callable[[Path, Path, dict[str, Any] | None, str], tuple[int, dict[str, Any], bool]],
    normalize_execution_mode: Callable[[str | None], str],
    schema: str,
    write_artifact: Callable[[Path, dict[str, Any]], Path],
    source_repro_artifact: str = "",
) -> dict[str, Any]:
    flow_file = _materialize_candidate_flow(project_root, plan_payload.get("candidate_flow", {}))
    execution_mode = normalize_execution_mode(execution_mode_raw)
    exit_code, raw_payload, _ = run_basic_flow_tool(project_root, flow_file, None, execution_mode)
    error_code, error_message, details = _extract_error(raw_payload)
    failed_phase = _classify_failed_phase(plan_payload, details)

    if bool(raw_payload.get("ok", False)):
        status = "bug_not_reproduced"
        reproduction_confirmed = False
    elif error_code in {ERR_ENGINE_RUNTIME_STALLED, ERR_TEARDOWN_VERIFICATION_FAILED}:
        status = "runtime_invalid"
        reproduction_confirmed = False
    elif error_code in {ERR_STEP_FAILED, ERR_TIMEOUT}:
        if failed_phase in {"setup", "precondition"}:
            status = "precondition_failed"
            reproduction_confirmed = False
        elif failed_phase == "trigger":
            status = "trigger_failed"
            reproduction_confirmed = False
        elif failed_phase == "postcondition":
            status = "bug_reproduced"
            reproduction_confirmed = True
        else:
            status = "runtime_invalid"
            reproduction_confirmed = False
    else:
        status = "runtime_invalid"
        reproduction_confirmed = False

    repro_gap = _build_repro_gap(plan_payload, status)
    refinement_plan = _build_refinement_plan(plan_payload, status, repro_gap)
    payload = {
        "schema": schema,
        "project_root": str(project_root.resolve()),
        "bug_summary": plan_payload.get("bug_summary", ""),
        "bug_identity": _bug_identity(plan_payload),
        "status": status,
        "reproduction_confirmed": reproduction_confirmed,
        "execution_mode": execution_mode,
        "flow_file": str(flow_file),
        "repro_flow_plan": plan_payload,
        "failed_phase": failed_phase,
        "repro_gap": repro_gap,
        "refinement_plan": refinement_plan,
        "raw_run_result": raw_payload,
        "run_exit_code": exit_code,
        "blocking_point": error_message if status in {"precondition_failed", "trigger_failed", "runtime_invalid"} else "",
        "next_action": (
            "inspect_failure_before_fixing"
            if status == "bug_reproduced"
            else (
                "inspect_precondition_failure"
                if status == "precondition_failed"
                else "inspect_trigger_failure"
                if status == "trigger_failed"
                else "inspect_runtime_failure"
                if status == "runtime_invalid"
                else str(refinement_plan.get("primary_action", "")).strip()
                or str(repro_gap.get("recommended_next_action", "")).strip()
                or "refine_repro_flow"
            )
        ),
    }
    if source_repro_artifact:
        payload["source_repro_artifact"] = source_repro_artifact
    artifact_file = write_artifact(project_root, payload)
    payload["artifact_file"] = str(artifact_file)
    return payload


def run_bug_repro_flow(
    project_root: Path,
    args: Any,
    *,
    plan_bug_repro_flow_fn: Callable[[Path, Any], dict[str, Any]] = plan_bug_repro_flow,
    run_basic_flow_tool: Callable[[Path, Path, dict[str, Any] | None, str], tuple[int, dict[str, Any], bool]],
    normalize_execution_mode: Callable[[str | None], str],
) -> dict[str, Any]:
    plan_payload = plan_bug_repro_flow_fn(project_root, args)
    return _execute_repro_plan(
        project_root=project_root,
        plan_payload=plan_payload,
        execution_mode_raw=getattr(args, "execution_mode", "play_mode"),
        run_basic_flow_tool=run_basic_flow_tool,
        normalize_execution_mode=normalize_execution_mode,
        schema="pointer_gpf.v2.repro_run.v1",
        write_artifact=_write_repro_result,
    )


def rerun_bug_repro_flow(
    project_root: Path,
    args: Any,
    *,
    load_repro_result_fn: Callable[[Path], dict[str, Any]] = load_repro_result,
    run_basic_flow_tool: Callable[[Path, Path, dict[str, Any] | None, str], tuple[int, dict[str, Any], bool]],
    normalize_execution_mode: Callable[[str | None], str],
) -> dict[str, Any]:
    source_payload = load_repro_result_fn(project_root)
    if not source_payload:
        return {
            "schema": "pointer_gpf.v2.repro_rerun.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": "",
            "status": "verification_not_ready",
            "reproduction_confirmed": False,
            "execution_mode": normalize_execution_mode(getattr(args, "execution_mode", "play_mode")),
            "flow_file": "",
            "repro_flow_plan": {},
            "failed_phase": "",
            "repro_gap": {},
            "refinement_plan": {},
            "raw_run_result": {},
            "run_exit_code": 0,
            "blocking_point": "no persisted repro result exists yet for this project",
            "next_action": "run_bug_repro_flow_first",
            "source_repro_artifact": "",
            "artifact_file": "",
        }

    plan_payload = source_payload.get("repro_flow_plan", {})
    if not isinstance(plan_payload, dict) or not isinstance(plan_payload.get("candidate_flow", {}), dict):
        return {
            "schema": "pointer_gpf.v2.repro_rerun.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": str(source_payload.get("bug_summary", "")).strip(),
            "status": "verification_not_ready",
            "reproduction_confirmed": False,
            "execution_mode": normalize_execution_mode(getattr(args, "execution_mode", "play_mode")),
            "flow_file": "",
            "repro_flow_plan": {},
            "failed_phase": "",
            "repro_gap": {},
            "refinement_plan": {},
            "raw_run_result": {},
            "run_exit_code": 0,
            "blocking_point": "the persisted repro result does not contain a reusable repro flow plan",
            "next_action": "run_bug_repro_flow_first",
            "source_repro_artifact": str(repro_result_path(project_root)),
            "artifact_file": "",
        }

    return _execute_repro_plan(
        project_root=project_root,
        plan_payload=plan_payload,
        execution_mode_raw=getattr(args, "execution_mode", None) or source_payload.get("execution_mode", "play_mode"),
        run_basic_flow_tool=run_basic_flow_tool,
        normalize_execution_mode=normalize_execution_mode,
        schema="pointer_gpf.v2.repro_rerun.v1",
        write_artifact=_write_repro_verification,
        source_repro_artifact=str(repro_result_path(project_root)),
    )
