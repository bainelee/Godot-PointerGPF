from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def _artifact_files(*payloads: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for payload in payloads:
        for key in ("artifact_file", "proposal_artifact", "application_artifact"):
            value = str(payload.get(key, "")).strip()
            if value and value not in out:
                out.append(value)
    return out


def _base_payload(project_root: Path, status: str, bug_summary: str) -> dict[str, Any]:
    return {
        "schema": "pointer_gpf.v2.reported_bug_repair.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": bug_summary,
        "status": status,
        "artifact_files": [],
        "blocking_point": "",
        "next_action": "",
    }


def repair_reported_bug(
    project_root: Path,
    args: Any,
    *,
    collect_bug_report_fn: Callable[[Path, Any], dict[str, Any]],
    observe_bug_context_fn: Callable[[Path, Any], dict[str, Any]],
    plan_bug_repro_flow_fn: Callable[[Path, Any], dict[str, Any]],
    run_bug_repro_flow_fn: Callable[[Path, Any], dict[str, Any]],
    plan_bug_fix_fn: Callable[[Path, Any], dict[str, Any]],
    apply_bug_fix_fn: Callable[[Path, Any], dict[str, Any]],
    rerun_bug_repro_flow_fn: Callable[[Path, Any], dict[str, Any]],
    run_bug_fix_regression_fn: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    intake = collect_bug_report_fn(project_root, args)
    bug_summary = str(intake.get("summary", "") or intake.get("bug_summary", "") or getattr(args, "bug_report", "")).strip()
    observation = observe_bug_context_fn(project_root, args)
    repro_plan = plan_bug_repro_flow_fn(project_root, args)
    evidence_status = str(repro_plan.get("model_evidence_plan_status", "")).strip()
    if evidence_status != "accepted":
        payload = _base_payload(project_root, "awaiting_model_evidence_plan", bug_summary)
        payload.update(
            {
                "bug_intake": intake,
                "observation": observation,
                "repro_plan": repro_plan,
                "blocking_point": "repair_reported_bug requires an accepted model evidence plan before running repro",
                "next_action": "provide_evidence_plan_json_or_file",
            }
        )
        return payload

    repro_result = run_bug_repro_flow_fn(project_root, args)
    repro_status = str(repro_result.get("status", "")).strip()
    if repro_status != "bug_reproduced":
        payload = _base_payload(project_root, "blocked", bug_summary)
        payload.update(
            {
                "bug_intake": intake,
                "observation": observation,
                "repro_plan": repro_plan,
                "repro_result": repro_result,
                "artifact_files": _artifact_files(repro_result),
                "blocking_point": f"repro did not confirm bug_reproduced; status={repro_status}",
                "next_action": str(repro_result.get("next_action", "refine_evidence_plan_or_repro_flow")).strip(),
            }
        )
        return payload

    fix_plan = plan_bug_fix_fn(project_root, args)
    fix_plan_status = str(fix_plan.get("status", "")).strip()
    if fix_plan_status != "fix_ready":
        payload = _base_payload(project_root, "blocked", bug_summary)
        payload.update(
            {
                "bug_intake": intake,
                "observation": observation,
                "repro_plan": repro_plan,
                "repro_result": repro_result,
                "fix_plan": fix_plan,
                "artifact_files": _artifact_files(repro_result),
                "blocking_point": f"plan_bug_fix did not return fix_ready; status={fix_plan_status}",
                "next_action": str(fix_plan.get("next_action", "inspect_repro_evidence")).strip(),
            }
        )
        return payload

    has_fix_proposal = bool(str(getattr(args, "fix_proposal_json", "") or "").strip() or str(getattr(args, "fix_proposal_file", "") or "").strip())
    if not has_fix_proposal:
        payload = _base_payload(project_root, "bug_reproduced_awaiting_fix_proposal", bug_summary)
        payload.update(
            {
                "bug_intake": intake,
                "observation": observation,
                "repro_plan": repro_plan,
                "repro_result": repro_result,
                "fix_plan": fix_plan,
                "artifact_files": _artifact_files(repro_result),
                "blocking_point": "bug is reproduced and fix plan is ready, but no bounded fix proposal was provided",
                "next_action": "provide_fix_proposal_json_or_file",
            }
        )
        return payload

    apply_result = apply_bug_fix_fn(project_root, args)
    apply_status = str(apply_result.get("status", "")).strip()
    if apply_status not in {"fix_applied", "already_aligned"}:
        payload = _base_payload(project_root, "blocked", bug_summary)
        payload.update(
            {
                "bug_intake": intake,
                "observation": observation,
                "repro_plan": repro_plan,
                "repro_result": repro_result,
                "fix_plan": fix_plan,
                "apply_result": apply_result,
                "artifact_files": _artifact_files(repro_result, apply_result),
                "blocking_point": f"apply_bug_fix did not apply a usable change; status={apply_status}",
                "next_action": str(apply_result.get("next_action", "provide_valid_fix_proposal")).strip(),
            }
        )
        return payload

    rerun_result = rerun_bug_repro_flow_fn(project_root, args)
    rerun_status = str(rerun_result.get("status", "")).strip()
    if rerun_status != "bug_not_reproduced":
        payload = _base_payload(project_root, "fix_applied_awaiting_repro_success", bug_summary)
        payload.update(
            {
                "bug_intake": intake,
                "observation": observation,
                "repro_plan": repro_plan,
                "repro_result": repro_result,
                "fix_plan": fix_plan,
                "apply_result": apply_result,
                "rerun_result": rerun_result,
                "artifact_files": _artifact_files(repro_result, apply_result, rerun_result),
                "blocking_point": f"fix was applied, but rerun status is {rerun_status}",
                "next_action": str(rerun_result.get("next_action", "inspect_rerun_failure")).strip(),
            }
        )
        return payload

    regression_result = run_bug_fix_regression_fn(project_root)
    regression_status = str(regression_result.get("status", "")).strip()
    payload = _base_payload(
        project_root,
        "fixed_and_verified" if regression_status == "passed" else "regression_failed",
        bug_summary,
    )
    payload.update(
        {
            "bug_intake": intake,
            "observation": observation,
            "repro_plan": repro_plan,
            "repro_result": repro_result,
            "fix_plan": fix_plan,
            "apply_result": apply_result,
            "rerun_result": rerun_result,
            "regression_result": regression_result,
            "artifact_files": _artifact_files(repro_result, apply_result, rerun_result, regression_result),
            "blocking_point": "" if regression_status == "passed" else "regression failed after bug-focused rerun passed",
            "next_action": "" if regression_status == "passed" else "inspect_regression_failure",
        }
    )
    return payload
