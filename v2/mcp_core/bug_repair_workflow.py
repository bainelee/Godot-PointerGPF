from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .repair_report_formatter import format_repair_report


def _compact_list(values: Any, *, limit: int = 8) -> list[Any]:
    if not isinstance(values, list):
        return []
    return values[:limit]


def _model_evidence_plan_instruction(args: Any, observation: dict[str, Any], repro_plan: dict[str, Any]) -> dict[str, Any]:
    static_observation = observation.get("project_static_observation", {})
    if not isinstance(static_observation, dict):
        static_observation = {}
    capabilities = observation.get("runtime_evidence_capabilities", {})
    if not isinstance(capabilities, dict):
        capabilities = {}

    return {
        "schema": "pointer_gpf.v2.model_evidence_plan_instruction.v1",
        "requested_output": "Provide --evidence-plan-json or --evidence-plan-file containing pointer_gpf.v2.model_evidence_plan.v1.",
        "allowed_actions": ["wait", "click", "sample", "observe", "callMethod", "aimAt", "shoot", "check"],
        "allowed_phases": ["pre_trigger", "trigger_window", "post_trigger", "final_check"],
        "constraints": {
            "max_steps": 12,
            "max_window_ms": 5000,
            "min_interval_ms": 16,
            "paths": "Use Godot node hints or res:// project paths only; do not use absolute filesystem paths.",
            "checks": "Every evidence-backed check should reference an evidenceKey produced by a sample or observe step.",
        },
        "bug_context": {
            "bug_report": str(getattr(args, "bug_report", "") or "").strip(),
            "expected_behavior": str(getattr(args, "expected_behavior", "") or "").strip(),
            "steps_to_trigger": str(getattr(args, "steps_to_trigger", "") or "").strip(),
            "location_scene": str(getattr(args, "location_scene", "") or "").strip(),
            "location_node": str(getattr(args, "location_node", "") or "").strip(),
            "location_script": str(getattr(args, "location_script", "") or "").strip(),
        },
        "project_fact_hints": {
            "candidate_files": _compact_list(static_observation.get("candidate_files", [])),
            "behavior_methods": _compact_list(static_observation.get("behavior_methods", [])),
            "scene_nodes": _compact_list(static_observation.get("scene_nodes", [])),
            "visual_state_surfaces": _compact_list(static_observation.get("visual_state_surfaces", [])),
            "runtime_evidence_target_candidates": _compact_list(static_observation.get("runtime_evidence_target_candidates", [])),
        },
        "runtime_evidence_capabilities": capabilities,
        "previous_rejection_reasons": _compact_list(repro_plan.get("model_evidence_plan_rejected_reasons", [])),
        "example": {
            "schema": "pointer_gpf.v2.model_evidence_plan.v1",
            "steps": [
                {
                    "id": "sample_state_before_trigger",
                    "phase": "pre_trigger",
                    "action": "sample",
                    "target": {"hint": "node_name:<visual_node>"},
                    "metric": {"kind": "shader_param", "param_name": "<param>"},
                    "windowMs": 120,
                    "intervalMs": 40,
                    "evidenceKey": "state_before_trigger",
                },
                {
                    "id": "aim_at_target",
                    "phase": "trigger_window",
                    "action": "aimAt",
                    "player": {"hint": "node_name:<player_node>"},
                    "target": {"hint": "node_name:<visual_node>"},
                },
                {
                    "id": "shoot_target",
                    "phase": "trigger_window",
                    "action": "shoot",
                    "player": {"hint": "node_name:<player_node>"},
                },
                {
                    "id": "sample_state_after_trigger",
                    "phase": "post_trigger",
                    "action": "sample",
                    "target": {"hint": "node_name:<visual_node>"},
                    "metric": {"kind": "shader_param", "param_name": "<param>"},
                    "windowMs": 240,
                    "intervalMs": 40,
                    "evidenceKey": "state_after_trigger",
                },
                {
                    "id": "check_state_after_trigger",
                    "phase": "final_check",
                    "action": "check",
                    "evidenceRef": "state_after_trigger",
                    "predicate": "value_seen",
                    "expected": "<expected_value>",
                },
            ],
        },
    }


def _model_fix_proposal_instruction(fix_plan: dict[str, Any], repro_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "pointer_gpf.v2.model_fix_proposal_instruction.v1",
        "requested_output": "Provide --fix-proposal-json or --fix-proposal-file containing a bounded edit proposal.",
        "constraints": {
            "candidate_file": "Choose one candidate_file from plan_bug_fix candidate files.",
            "edits": "Use small replace edits with unique old_text matches.",
            "scope": "Do not edit files that are not listed in the fix plan candidate files.",
            "verification": "The same bug-focused repro and regression will run after applying the proposal.",
        },
        "candidate_files": _compact_list(fix_plan.get("candidate_files", []), limit=10),
        "fix_goals": _compact_list(fix_plan.get("fix_goals", []), limit=10),
        "acceptance_checks": _compact_list(fix_plan.get("acceptance_checks", []), limit=10),
        "runtime_evidence_summary": repro_result.get("runtime_evidence_summary", {}),
        "example": {
            "schema": "pointer_gpf.v2.model_fix_proposal.v1",
            "candidate_file": "res://scripts/example.gd",
            "edits": [
                {
                    "kind": "replace",
                    "old_text": "\treturn  # remove the incorrect early return\n",
                    "new_text": "",
                    "reason": "Allow the existing feedback update code to run.",
                }
            ],
        },
    }


def _artifact_files(*payloads: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for payload in payloads:
        for key in ("artifact_file", "proposal_artifact", "application_artifact"):
            value = str(payload.get(key, "")).strip()
            if value and value not in out:
                out.append(value)
    return out


def _artifact_summary(*payloads: dict[str, Any]) -> dict[str, Any]:
    by_stage: dict[str, str] = {}
    files: list[str] = []
    for stage, payload in zip(("repro", "apply", "rerun", "regression"), payloads):
        for key in ("artifact_file", "proposal_artifact", "application_artifact"):
            value = str(payload.get(key, "")).strip()
            if not value:
                continue
            label = stage if key == "artifact_file" else key.replace("_artifact", "")
            by_stage[f"{label}_artifact"] = value
            if value not in files:
                files.append(value)
    return {
        "files": files,
        "by_stage": by_stage,
    }


def _runtime_evidence_ids(payload: dict[str, Any]) -> list[str]:
    summary = payload.get("runtime_evidence_summary", {})
    if isinstance(summary, dict):
        by_check = summary.get("evidence_by_check_id", {})
        if isinstance(by_check, dict):
            ids: list[str] = []
            for value in by_check.values():
                if isinstance(value, str) and value not in ids:
                    ids.append(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and item not in ids:
                            ids.append(item)
            if ids:
                return ids
    records = payload.get("runtime_evidence_records", [])
    if isinstance(records, list):
        ids = []
        for record in records:
            if not isinstance(record, dict):
                continue
            evidence_id = str(record.get("evidence_id", "")).strip()
            if evidence_id and evidence_id not in ids:
                ids.append(evidence_id)
        return ids
    return []


def _failed_check_ids(payload: dict[str, Any]) -> list[str]:
    check_summary = payload.get("check_summary", {})
    if not isinstance(check_summary, dict):
        return []
    values = check_summary.get("failed_check_ids", [])
    return [str(value) for value in values if str(value).strip()] if isinstance(values, list) else []


def _repair_summary(
    *,
    status: str,
    bug_summary: str,
    intake: dict[str, Any],
    repro_result: dict[str, Any] | None = None,
    fix_plan: dict[str, Any] | None = None,
    apply_result: dict[str, Any] | None = None,
    rerun_result: dict[str, Any] | None = None,
    regression_result: dict[str, Any] | None = None,
    artifact_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repro_result = repro_result or {}
    fix_plan = fix_plan or {}
    apply_result = apply_result or {}
    rerun_result = rerun_result or {}
    regression_result = regression_result or {}
    applied_changes = apply_result.get("applied_changes", [])
    if not isinstance(applied_changes, list):
        applied_changes = []
    candidate_files = fix_plan.get("candidate_files", [])
    if not isinstance(candidate_files, list):
        candidate_files = []
    return {
        "schema": "pointer_gpf.v2.repair_summary.v1",
        "status": status,
        "bug_summary": bug_summary,
        "bug_source": str(intake.get("bug_source", "")).strip(),
        "injected_bug_kind": str(intake.get("injected_bug_kind", "")).strip(),
        "round_id": str(intake.get("round_id", "")).strip(),
        "bug_id": str(intake.get("bug_id", "")).strip(),
        "repro": {
            "status": str(repro_result.get("status", "")).strip(),
            "failed_phase": str(repro_result.get("failed_phase", "")).strip(),
            "failed_check_ids": _failed_check_ids(repro_result),
            "runtime_evidence_ids": _runtime_evidence_ids(repro_result),
            "artifact_file": str(repro_result.get("artifact_file", "")).strip(),
        },
        "fix_plan": {
            "status": str(fix_plan.get("status", "")).strip(),
            "candidate_files": _compact_list(candidate_files, limit=10),
            "fix_goals": _compact_list(fix_plan.get("fix_goals", []), limit=10),
        },
        "apply": {
            "status": str(apply_result.get("status", "")).strip(),
            "applied_changes": _compact_list(applied_changes, limit=10),
            "proposal_artifact": str(apply_result.get("proposal_artifact", "")).strip(),
            "application_artifact": str(apply_result.get("application_artifact", "")).strip(),
        },
        "rerun": {
            "status": str(rerun_result.get("status", "")).strip(),
            "runtime_evidence_ids": _runtime_evidence_ids(rerun_result),
            "artifact_file": str(rerun_result.get("artifact_file", "")).strip(),
        },
        "regression": {
            "status": str(regression_result.get("status", "")).strip(),
            "artifact_file": str(regression_result.get("artifact_file", "")).strip(),
        },
        "artifact_summary": artifact_summary or {"files": [], "by_stage": {}},
    }


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
                "model_evidence_plan_instruction": _model_evidence_plan_instruction(args, observation, repro_plan),
            }
        )
        return payload

    repro_result = run_bug_repro_flow_fn(project_root, args)
    repro_status = str(repro_result.get("status", "")).strip()
    if repro_status != "bug_reproduced":
        artifact_summary = _artifact_summary(repro_result)
        repair_summary = _repair_summary(
            status="blocked",
            bug_summary=bug_summary,
            intake=intake,
            repro_result=repro_result,
            artifact_summary=artifact_summary,
        )
        payload = _base_payload(project_root, "blocked", bug_summary)
        payload.update(
            {
                "bug_intake": intake,
                "observation": observation,
                "repro_plan": repro_plan,
                "repro_result": repro_result,
                "artifact_files": artifact_summary["files"],
                "artifact_summary": artifact_summary,
                "repair_summary": repair_summary,
                "user_report": format_repair_report({"status": "blocked", "bug_summary": bug_summary, "repair_summary": repair_summary, "artifact_summary": artifact_summary}),
                "blocking_point": f"repro did not confirm bug_reproduced; status={repro_status}",
                "next_action": str(repro_result.get("next_action", "refine_evidence_plan_or_repro_flow")).strip(),
            }
        )
        return payload

    fix_plan = plan_bug_fix_fn(project_root, args)
    fix_plan_status = str(fix_plan.get("status", "")).strip()
    if fix_plan_status != "fix_ready":
        artifact_summary = _artifact_summary(repro_result)
        repair_summary = _repair_summary(
            status="blocked",
            bug_summary=bug_summary,
            intake=intake,
            repro_result=repro_result,
            fix_plan=fix_plan,
            artifact_summary=artifact_summary,
        )
        payload = _base_payload(project_root, "blocked", bug_summary)
        payload.update(
            {
                "bug_intake": intake,
                "observation": observation,
                "repro_plan": repro_plan,
                "repro_result": repro_result,
                "fix_plan": fix_plan,
                "artifact_files": artifact_summary["files"],
                "artifact_summary": artifact_summary,
                "repair_summary": repair_summary,
                "user_report": format_repair_report({"status": "blocked", "bug_summary": bug_summary, "repair_summary": repair_summary, "artifact_summary": artifact_summary}),
                "blocking_point": f"plan_bug_fix did not return fix_ready; status={fix_plan_status}",
                "next_action": str(fix_plan.get("next_action", "inspect_repro_evidence")).strip(),
            }
        )
        return payload

    has_fix_proposal = bool(str(getattr(args, "fix_proposal_json", "") or "").strip() or str(getattr(args, "fix_proposal_file", "") or "").strip())
    if not has_fix_proposal:
        artifact_summary = _artifact_summary(repro_result)
        repair_summary = _repair_summary(
            status="bug_reproduced_awaiting_fix_proposal",
            bug_summary=bug_summary,
            intake=intake,
            repro_result=repro_result,
            fix_plan=fix_plan,
            artifact_summary=artifact_summary,
        )
        payload = _base_payload(project_root, "bug_reproduced_awaiting_fix_proposal", bug_summary)
        payload.update(
            {
                "bug_intake": intake,
                "observation": observation,
                "repro_plan": repro_plan,
                "repro_result": repro_result,
                "fix_plan": fix_plan,
                "artifact_files": artifact_summary["files"],
                "artifact_summary": artifact_summary,
                "repair_summary": repair_summary,
                "user_report": format_repair_report({"status": "bug_reproduced_awaiting_fix_proposal", "bug_summary": bug_summary, "repair_summary": repair_summary, "artifact_summary": artifact_summary}),
                "blocking_point": "bug is reproduced and fix plan is ready, but no bounded fix proposal was provided",
                "next_action": "provide_fix_proposal_json_or_file",
                "model_fix_proposal_instruction": _model_fix_proposal_instruction(fix_plan, repro_result),
            }
        )
        return payload

    apply_result = apply_bug_fix_fn(project_root, args)
    apply_status = str(apply_result.get("status", "")).strip()
    if apply_status not in {"fix_applied", "already_aligned"}:
        artifact_summary = _artifact_summary(repro_result, apply_result)
        repair_summary = _repair_summary(
            status="blocked",
            bug_summary=bug_summary,
            intake=intake,
            repro_result=repro_result,
            fix_plan=fix_plan,
            apply_result=apply_result,
            artifact_summary=artifact_summary,
        )
        payload = _base_payload(project_root, "blocked", bug_summary)
        payload.update(
            {
                "bug_intake": intake,
                "observation": observation,
                "repro_plan": repro_plan,
                "repro_result": repro_result,
                "fix_plan": fix_plan,
                "apply_result": apply_result,
                "artifact_files": artifact_summary["files"],
                "artifact_summary": artifact_summary,
                "repair_summary": repair_summary,
                "user_report": format_repair_report({"status": "blocked", "bug_summary": bug_summary, "repair_summary": repair_summary, "artifact_summary": artifact_summary}),
                "blocking_point": f"apply_bug_fix did not apply a usable change; status={apply_status}",
                "next_action": str(apply_result.get("next_action", "provide_valid_fix_proposal")).strip(),
            }
        )
        return payload

    rerun_result = rerun_bug_repro_flow_fn(project_root, args)
    rerun_status = str(rerun_result.get("status", "")).strip()
    if rerun_status != "bug_not_reproduced":
        artifact_summary = _artifact_summary(repro_result, apply_result, rerun_result)
        repair_summary = _repair_summary(
            status="fix_applied_awaiting_repro_success",
            bug_summary=bug_summary,
            intake=intake,
            repro_result=repro_result,
            fix_plan=fix_plan,
            apply_result=apply_result,
            rerun_result=rerun_result,
            artifact_summary=artifact_summary,
        )
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
                "artifact_files": artifact_summary["files"],
                "artifact_summary": artifact_summary,
                "repair_summary": repair_summary,
                "user_report": format_repair_report({"status": "fix_applied_awaiting_repro_success", "bug_summary": bug_summary, "repair_summary": repair_summary, "artifact_summary": artifact_summary}),
                "blocking_point": f"fix was applied, but rerun status is {rerun_status}",
                "next_action": str(rerun_result.get("next_action", "inspect_rerun_failure")).strip(),
            }
        )
        return payload

    regression_result = run_bug_fix_regression_fn(project_root)
    regression_status = str(regression_result.get("status", "")).strip()
    final_status = "fixed_and_verified" if regression_status == "passed" else "regression_failed"
    artifact_summary = _artifact_summary(repro_result, apply_result, rerun_result, regression_result)
    repair_summary = _repair_summary(
        status=final_status,
        bug_summary=bug_summary,
        intake=intake,
        repro_result=repro_result,
        fix_plan=fix_plan,
        apply_result=apply_result,
        rerun_result=rerun_result,
        regression_result=regression_result,
        artifact_summary=artifact_summary,
    )
    payload = _base_payload(
        project_root,
        final_status,
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
            "artifact_files": artifact_summary["files"],
            "artifact_summary": artifact_summary,
            "repair_summary": repair_summary,
            "user_report": format_repair_report({"status": final_status, "bug_summary": bug_summary, "repair_summary": repair_summary, "artifact_summary": artifact_summary}),
            "blocking_point": "" if regression_status == "passed" else "regression failed after bug-focused rerun passed",
            "next_action": "" if regression_status == "passed" else "inspect_regression_failure",
        }
    )
    return payload
