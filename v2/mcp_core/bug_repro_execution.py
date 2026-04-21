from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .contracts import ERR_ENGINE_RUNTIME_STALLED, ERR_STEP_FAILED, ERR_TIMEOUT
from .bug_repro_flow import plan_bug_repro_flow


def _extract_step_hint(step: dict[str, Any]) -> str:
    hint = ""
    if isinstance(step.get("until"), dict):
        hint = str(step["until"].get("hint", "")).strip()
    if not hint:
        hint = str(step.get("hint", "")).strip()
    return hint


def _materialize_candidate_flow(project_root: Path, candidate_flow: dict[str, Any]) -> Path:
    target = (project_root / "pointer_gpf" / "tmp" / "planned_bug_repro_flow.json").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(candidate_flow, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _assertion_step_ids(plan_payload: dict[str, Any]) -> set[str]:
    assertion_hints = {
        str(item.get("runtime_check", {}).get("hint", "")).strip()
        for item in plan_payload.get("assertion_set", {}).get("assertions", [])
        if isinstance(item, dict)
    }
    assertion_hints.discard("")
    step_ids: set[str] = set()
    for step in plan_payload.get("candidate_flow", {}).get("steps", []):
        if not isinstance(step, dict):
            continue
        if _extract_step_hint(step) in assertion_hints:
            step_ids.add(str(step.get("id", "")).strip())
    step_ids.discard("")
    return step_ids


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
            summary = "repro flow passed all currently covered assertions without exposing the bug"
            recommended_next_action = "increase trigger specificity or introduce a stronger post-click assertion if the bug is still suspected"
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
            if not assertion_name:
                continue
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
            if not assertion_name:
                continue
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


def run_bug_repro_flow(
    project_root: Path,
    args: Any,
    *,
    plan_bug_repro_flow_fn: Callable[[Path, Any], dict[str, Any]] = plan_bug_repro_flow,
    run_basic_flow_tool: Callable[[Path, Path, dict[str, Any] | None, str], tuple[int, dict[str, Any], bool]],
    normalize_execution_mode: Callable[[str | None], str],
) -> dict[str, Any]:
    plan_payload = plan_bug_repro_flow_fn(project_root, args)
    flow_file = _materialize_candidate_flow(project_root, plan_payload.get("candidate_flow", {}))
    execution_mode = normalize_execution_mode(getattr(args, "execution_mode", "play_mode"))
    exit_code, raw_payload, _ = run_basic_flow_tool(project_root, flow_file, None, execution_mode)
    error = raw_payload.get("error", {}) if isinstance(raw_payload, dict) else {}
    details = error.get("details", {}) if isinstance(error, dict) else {}
    step_id = str(details.get("step_id", "")).strip() if isinstance(details, dict) else ""
    assertion_step_ids = _assertion_step_ids(plan_payload)

    if bool(raw_payload.get("ok", False)):
        status = "bug_not_reproduced"
        reproduction_confirmed = False
    elif str(error.get("code", "")) in {ERR_STEP_FAILED, ERR_TIMEOUT} and step_id in assertion_step_ids:
        status = "bug_reproduced"
        reproduction_confirmed = True
    elif str(error.get("code", "")) == ERR_ENGINE_RUNTIME_STALLED:
        status = "flow_invalid"
        reproduction_confirmed = False
    else:
        status = "flow_invalid"
        reproduction_confirmed = False

    repro_gap = _build_repro_gap(plan_payload, status)
    refinement_plan = _build_refinement_plan(plan_payload, status, repro_gap)

    return {
        "schema": "pointer_gpf.v2.repro_run.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": plan_payload.get("bug_summary", ""),
        "status": status,
        "reproduction_confirmed": reproduction_confirmed,
        "execution_mode": execution_mode,
        "flow_file": str(flow_file),
        "repro_flow_plan": plan_payload,
        "repro_gap": repro_gap,
        "refinement_plan": refinement_plan,
        "raw_run_result": raw_payload,
        "run_exit_code": exit_code,
        "blocking_point": str(error.get("message", "")).strip() if status == "flow_invalid" else "",
        "next_action": (
            "inspect_failure_before_fixing"
            if status == "bug_reproduced"
            else str(refinement_plan.get("primary_action", "")).strip()
            or str(repro_gap.get("recommended_next_action", "")).strip()
            or "refine_repro_flow"
        ),
    }
