from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .bug_checks import build_executable_checks, summarize_check_results
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


def _runtime_evidence_payload(raw_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(raw_payload, dict):
        return [], {}
    sources: list[dict[str, Any]] = [raw_payload]
    result = raw_payload.get("result", {})
    if isinstance(result, dict):
        sources.append(result)

    records: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for source in sources:
        raw_records = source.get("runtime_evidence_records", [])
        if isinstance(raw_records, list):
            records.extend([dict(item) for item in raw_records if isinstance(item, dict)])
        if not summary and isinstance(source.get("runtime_evidence_summary", {}), dict):
            summary = dict(source.get("runtime_evidence_summary", {}))

    if not summary:
        failed = [
            str(item.get("evidence_id", "") or item.get("id", "")).strip()
            for item in records
            if isinstance(item, dict) and str(item.get("status", "")).strip().lower() in {"failed", "inconclusive"}
        ]
        summary = {
            "record_count": len(records),
            "failed_evidence_ids": [item for item in failed if item],
            "inconclusive_evidence_ids": [
                str(item.get("evidence_id", "") or item.get("id", "")).strip()
                for item in records
                if isinstance(item, dict) and str(item.get("status", "")).strip().lower() == "inconclusive"
            ],
            "evidence_by_check_id": {},
        }
    return records, summary


def _runtime_evidence_catalog(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for check in checks:
        evidence_ref = str(check.get("evidence_ref", "")).strip()
        check_type = str(check.get("check_type", "")).strip()
        if not evidence_ref and not check_type:
            continue
        catalog.append(
            {
                "check_id": str(check.get("check_id", "")).strip(),
                "evidence_ref": evidence_ref,
                "check_type": check_type,
                "action": str(check.get("action", "")).strip(),
                "target": check.get("target", {}) if isinstance(check.get("target", {}), dict) else {},
                "metric": check.get("metric", {}) if isinstance(check.get("metric", {}), dict) else {},
                "predicate": check.get("predicate", {}) if isinstance(check.get("predicate", {}), dict) else {},
                "sample_plan": check.get("sample_plan", {}) if isinstance(check.get("sample_plan", {}), dict) else {},
            }
        )
    return catalog


def _attach_evidence_to_check_results(
    check_result_bundle: dict[str, Any],
    evidence_records: list[dict[str, Any]],
) -> dict[str, Any]:
    by_ref: dict[str, list[dict[str, Any]]] = {}
    for record in evidence_records:
        evidence_id = str(record.get("evidence_id", "") or record.get("id", "") or record.get("evidenceRef", "")).strip()
        if not evidence_id:
            continue
        by_ref.setdefault(evidence_id, []).append(record)

    results = check_result_bundle.get("results", [])
    if not isinstance(results, list):
        return check_result_bundle
    for result in results:
        if not isinstance(result, dict):
            continue
        evidence_ref = str(result.get("evidence_ref", "")).strip()
        if not evidence_ref:
            continue
        result["evidence_ref"] = evidence_ref
        result["runtime_evidence"] = by_ref.get(evidence_ref, [])
        evidence = result.get("evidence", {})
        if isinstance(evidence, dict):
            evidence["evidence_ref"] = evidence_ref
            evidence["runtime_evidence_count"] = len(by_ref.get(evidence_ref, []))
    return check_result_bundle


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


def _bug_round_metadata(plan_payload: dict[str, Any]) -> dict[str, str]:
    intake = plan_payload.get("assertion_set", {}).get("bug_analysis", {}).get("bug_intake", {})
    if not isinstance(intake, dict):
        return {
            "round_id": "",
            "bug_id": "",
            "bug_source": "pre_existing",
            "injected_bug_kind": "",
            "bug_case_file": "",
        }
    return {
        "round_id": str(intake.get("round_id", "")).strip(),
        "bug_id": str(intake.get("bug_id", "")).strip(),
        "bug_source": str(intake.get("bug_source", "pre_existing")).strip() or "pre_existing",
        "injected_bug_kind": str(intake.get("injected_bug_kind", "")).strip(),
        "bug_case_file": str(intake.get("bug_case_file", "")).strip(),
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
    checks = build_executable_checks(
        plan_payload.get("assertion_set", {}) if isinstance(plan_payload.get("assertion_set", {}), dict) else {},
        plan_payload.get("candidate_flow", {}) if isinstance(plan_payload.get("candidate_flow", {}), dict) else {},
    )
    evidence_records, evidence_summary = _runtime_evidence_payload(raw_payload)
    check_result_bundle = summarize_check_results(
        plan_payload.get("candidate_flow", {}) if isinstance(plan_payload.get("candidate_flow", {}), dict) else {},
        checks,
        run_ok=bool(raw_payload.get("ok", False)),
        failed_step_id=str(details.get("step_id", "")).strip(),
        failure_status=status,
        error_code=error_code,
        error_message=error_message,
    )
    check_result_bundle = _attach_evidence_to_check_results(check_result_bundle, evidence_records)
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
        "executable_checks": checks,
        "check_results": check_result_bundle.get("results", []),
        "check_summary": check_result_bundle.get("summary", {}),
        "runtime_evidence_catalog": _runtime_evidence_catalog(checks),
        "runtime_evidence_records": evidence_records,
        "runtime_evidence_summary": evidence_summary,
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
    payload.update(_bug_round_metadata(plan_payload))
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
            "round_id": "",
            "bug_id": "",
            "bug_source": "pre_existing",
            "injected_bug_kind": "",
            "bug_case_file": "",
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
            "round_id": str(source_payload.get("round_id", "")).strip(),
            "bug_id": str(source_payload.get("bug_id", "")).strip(),
            "bug_source": str(source_payload.get("bug_source", "pre_existing")).strip() or "pre_existing",
            "injected_bug_kind": str(source_payload.get("injected_bug_kind", "")).strip(),
            "bug_case_file": str(source_payload.get("bug_case_file", "")).strip(),
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
