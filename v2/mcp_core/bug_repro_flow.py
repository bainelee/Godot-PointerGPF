from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .basicflow_assets import BasicFlowAssetError, basicflow_paths, load_basicflow_assets
from .bug_assertions import define_bug_assertions
from .bug_evidence_plan import load_model_evidence_plan


def _load_base_flow(project_root: Path) -> tuple[dict[str, Any], str]:
    try:
        assets = load_basicflow_assets(project_root)
    except BasicFlowAssetError:
        return (
            {
                "flowId": "planned_bug_repro_flow",
                "name": "Planned Bug Repro Flow",
                "description": "Generated repro flow candidate",
                "steps": [
                    {"id": "launch_game", "action": "launchGame"},
                    {"id": "close_project", "action": "closeProject"},
                ],
            },
            "new_minimal_repro_flow",
        )
    return deepcopy(assets.get("flow", {})), "reuse_project_basicflow"


def _find_close_index(steps: list[dict[str, Any]]) -> int:
    for index, step in enumerate(steps):
        if str(step.get("action", "")).strip().lower() == "closeproject":
            return index
    return len(steps)


def _find_first_trigger_index(steps: list[dict[str, Any]]) -> int | None:
    for index, step in enumerate(steps):
        if str(step.get("action", "")).strip().lower() == "click":
            return index
    return None


def _runtime_hint(step: dict[str, Any]) -> str:
    if isinstance(step.get("until"), dict):
        hint = str(step["until"].get("hint", "")).strip()
        if hint:
            return hint
    return str(step.get("hint", "")).strip()


def _existing_runtime_hints(steps: list[dict[str, Any]]) -> set[str]:
    hints: set[str] = set()
    for step in steps:
        hint = _runtime_hint(step)
        if hint:
            hints.add(hint)
    return hints


def _assertion_step(assertion: dict[str, Any], prefix: str, index: int) -> tuple[dict[str, Any], str] | None:
    runtime_check = assertion.get("runtime_check", {})
    if not isinstance(runtime_check, dict) or not bool(runtime_check.get("supported", False)):
        return None
    hint = str(runtime_check.get("hint", "")).strip()
    if not hint:
        return None
    action = str(runtime_check.get("action", "check")).strip() or "check"
    step_id = f"{prefix}_{index}_{assertion.get('id', 'runtime_check')}"
    if action == "wait":
        return (
            {
                "id": step_id,
                "action": "wait",
                "until": {"hint": hint},
                "timeoutMs": 5000,
            },
            hint,
        )
    return (
        {
            "id": step_id,
            "action": "check",
            "hint": hint,
        },
        hint,
    )


def _build_execution_contract(candidate_steps: list[dict[str, Any]]) -> dict[str, Any]:
    first_trigger_index = _find_first_trigger_index(candidate_steps)
    setup_step_ids: list[str] = []
    precondition_step_ids: list[str] = []
    trigger_step_ids: list[str] = []
    postcondition_step_ids: list[str] = []
    close_step_ids: list[str] = []

    for index, step in enumerate(candidate_steps):
        step_id = str(step.get("id", "")).strip()
        if not step_id:
            continue
        action = str(step.get("action", "")).strip().lower()
        if action == "closeproject":
            close_step_ids.append(step_id)
        elif action == "click":
            trigger_step_ids.append(step_id)
        elif first_trigger_index is None or index < first_trigger_index:
            if action in {"wait", "check", "sample", "observe"}:
                precondition_step_ids.append(step_id)
            else:
                setup_step_ids.append(step_id)
        else:
            postcondition_step_ids.append(step_id)

    return {
        "schema": "pointer_gpf.v2.repro_execution_contract.v1",
        "setup_step_ids": setup_step_ids,
        "precondition_step_ids": precondition_step_ids,
        "trigger_step_ids": trigger_step_ids,
        "postcondition_step_ids": postcondition_step_ids,
        "close_step_ids": close_step_ids,
        "trigger_started": bool(trigger_step_ids),
        "first_trigger_step_id": trigger_step_ids[0] if trigger_step_ids else "",
    }


def _location_node(args: Any) -> str:
    return str(getattr(args, "location_node", "") or "").strip()


def _explicit_trigger_step(args: Any) -> dict[str, Any] | None:
    node_name = _location_node(args)
    if not node_name:
        return None
    return {
        "id": f"trigger_click_{node_name.lower()}",
        "action": "click",
        "target": {"hint": f"node_name:{node_name}"},
    }


def _model_evidence_steps_by_phase(evidence_plan_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    plan = evidence_plan_payload.get("plan", {}) if isinstance(evidence_plan_payload, dict) else {}
    raw_steps = plan.get("steps", []) if isinstance(plan, dict) else []
    out = {
        "pre_trigger": [],
        "trigger_window": [],
        "post_trigger": [],
        "final_check": [],
    }
    if not isinstance(raw_steps, list):
        return out
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            continue
        phase = str(raw_step.get("phase", "") or raw_step.get("modelEvidencePhase", "") or "post_trigger").strip()
        if phase not in out:
            phase = "post_trigger"
        out[phase].append(deepcopy(raw_step))
    return out


def _materialize_trigger_window_steps(raw_steps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    before_trigger: list[dict[str, Any]] = []
    after_trigger: list[dict[str, Any]] = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            continue
        action = str(raw_step.get("action", "")).strip().lower()
        if action != "observe":
            after_trigger.append(deepcopy(raw_step))
            continue
        evidence_key = str(raw_step.get("evidenceKey", "") or raw_step.get("evidence_key", "") or raw_step.get("evidenceRef", "") or raw_step.get("evidence_ref", "")).strip()
        step_id = str(raw_step.get("id", "")).strip() or f"observe_{evidence_key}"
        start_step = deepcopy(raw_step)
        start_step["id"] = f"{step_id}_start"
        start_step["mode"] = "start"
        start_step["phase"] = "pre_trigger"
        start_step["modelEvidencePhase"] = "trigger_window"
        collect_step = {
            "id": f"{step_id}_collect",
            "action": "observe",
            "mode": "collect",
            "phase": "post_trigger",
            "modelEvidencePhase": "trigger_window",
            "source": "model_evidence_plan",
            "evidenceRef": evidence_key,
            "evidenceKey": evidence_key,
        }
        before_trigger.append(start_step)
        after_trigger.append(collect_step)
    return before_trigger, after_trigger


def _evidence_refs_for_steps(steps: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    produced: list[str] = []
    required: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action", "")).strip().lower()
        evidence_key = str(step.get("evidenceKey", "") or step.get("evidence_key", "")).strip()
        evidence_ref = str(step.get("evidenceRef", "") or step.get("evidence_ref", "")).strip()
        mode = str(step.get("mode", "")).strip().lower()
        if action in {"sample", "observe"} and mode != "collect" and evidence_key and evidence_key not in produced:
            produced.append(evidence_key)
        if action == "observe" and mode == "collect" and evidence_ref and evidence_ref not in produced:
            produced.append(evidence_ref)
        if action == "check" and evidence_ref and evidence_ref not in required:
            required.append(evidence_ref)
    return produced, required


def _model_step_coverage(steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        out.append(
            {
                "step_id": str(step.get("id", "")).strip(),
                "phase": str(step.get("phase", "") or step.get("modelEvidencePhase", "")).strip(),
                "action": str(step.get("action", "")).strip(),
                "status": "planned",
                "evidence_ref": str(step.get("evidenceRef", "") or step.get("evidence_ref", "") or step.get("evidenceKey", "") or step.get("evidence_key", "")).strip(),
            }
        )
    return out


def plan_bug_repro_flow(project_root: Path, args: Any) -> dict[str, Any]:
    assertion_set = define_bug_assertions(project_root, args)
    evidence_plan_payload = load_model_evidence_plan(project_root, args)
    evidence_steps_by_phase = _model_evidence_steps_by_phase(evidence_plan_payload)
    trigger_window_start_steps, trigger_window_collect_steps = _materialize_trigger_window_steps(
        evidence_steps_by_phase["trigger_window"]
    )
    base_flow, strategy = _load_base_flow(project_root)
    steps = [step for step in base_flow.get("steps", []) if isinstance(step, dict)]
    close_index = _find_close_index(steps)
    core_steps = steps[:close_index]
    close_steps = steps[close_index:]
    existing_hints = _existing_runtime_hints(core_steps)
    first_trigger_index = _find_first_trigger_index(core_steps)

    planned_precondition_steps: list[dict[str, Any]] = []
    planned_postcondition_steps: list[dict[str, Any]] = []
    assertion_coverage: list[dict[str, Any]] = []
    unsupported_assertions: list[str] = []

    for index, assertion in enumerate(assertion_set.get("preconditions", [])):
        if not isinstance(assertion, dict):
            continue
        built = _assertion_step(assertion, "precondition", index)
        assertion_id = str(assertion.get("id", f"precondition_{index}"))
        if built is None:
            unsupported_assertions.append(assertion_id)
            continue
        step, hint = built
        if hint in existing_hints:
            assertion_coverage.append(
                {
                    "assertion_id": assertion_id,
                    "status": "already_covered_by_base_flow",
                    "reason": f"base flow already contains runtime hint {hint}",
                    "supporting_assertions": [],
                }
            )
            continue
        planned_precondition_steps.append(step)
        existing_hints.add(hint)
        assertion_coverage.append(
            {
                "assertion_id": assertion_id,
                "status": "covered_by_planned_step",
                "reason": "repro planner added an explicit precondition step for this assertion",
                "supporting_assertions": [],
            }
        )

    for index, assertion in enumerate(assertion_set.get("postconditions", [])):
        if not isinstance(assertion, dict):
            continue
        built = _assertion_step(assertion, "postcondition", index)
        assertion_id = str(assertion.get("id", f"postcondition_{index}"))
        if built is None:
            unsupported_assertions.append(assertion_id)
            continue
        step, hint = built
        if hint in existing_hints:
            assertion_coverage.append(
                {
                    "assertion_id": assertion_id,
                    "status": "already_covered_by_base_flow",
                    "reason": f"base flow already contains runtime hint {hint}",
                    "supporting_assertions": [],
                }
            )
            continue
        planned_postcondition_steps.append(step)
        existing_hints.add(hint)
        assertion_coverage.append(
            {
                "assertion_id": assertion_id,
                "status": "covered_by_planned_step",
                "reason": "repro planner added an explicit postcondition step for this assertion",
                "supporting_assertions": [],
            }
        )

    planned_trigger = None
    if first_trigger_index is None:
        planned_trigger = _explicit_trigger_step(args)
        first_trigger_index = len(core_steps) + len(planned_precondition_steps) if planned_trigger is not None else None

    if first_trigger_index is None:
        candidate_core = (
            core_steps
            + planned_precondition_steps
            + evidence_steps_by_phase["pre_trigger"]
            + trigger_window_start_steps
            + planned_postcondition_steps
            + trigger_window_collect_steps
            + evidence_steps_by_phase["post_trigger"]
            + evidence_steps_by_phase["final_check"]
        )
    else:
        trigger_insert_index = _find_first_trigger_index(core_steps)
        if trigger_insert_index is None:
            candidate_core = core_steps + planned_precondition_steps + evidence_steps_by_phase["pre_trigger"] + trigger_window_start_steps
            if planned_trigger is not None:
                candidate_core.append(planned_trigger)
            candidate_core.extend(planned_postcondition_steps)
            candidate_core.extend(trigger_window_collect_steps)
            candidate_core.extend(evidence_steps_by_phase["post_trigger"])
            candidate_core.extend(evidence_steps_by_phase["final_check"])
        else:
            candidate_core = (
                core_steps[:trigger_insert_index]
                + planned_precondition_steps
                + evidence_steps_by_phase["pre_trigger"]
                + trigger_window_start_steps
                + core_steps[trigger_insert_index:]
                + planned_postcondition_steps
                + trigger_window_collect_steps
                + evidence_steps_by_phase["post_trigger"]
                + evidence_steps_by_phase["final_check"]
            )

    candidate_steps = candidate_core + close_steps
    flow_file = basicflow_paths(project_root).flow_file
    candidate_flow = {
        "flowId": "planned_bug_repro_flow",
        "name": "Planned Bug Repro Flow",
        "description": f"Planned repro flow for: {assertion_set.get('bug_summary', '')}",
        "steps": candidate_steps,
    }

    model_evidence_steps = (
        evidence_steps_by_phase["pre_trigger"]
        + trigger_window_start_steps
        + trigger_window_collect_steps
        + evidence_steps_by_phase["post_trigger"]
        + evidence_steps_by_phase["final_check"]
    )
    evidence_refs_produced, evidence_refs_required = _evidence_refs_for_steps(model_evidence_steps)
    planned_step_count = len(planned_precondition_steps) + len(planned_postcondition_steps) + (1 if planned_trigger is not None else 0)
    repro_readiness = "blocked_by_unsupported_assertions" if unsupported_assertions else "ready_for_repro_run"
    if str(evidence_plan_payload.get("status", "")).strip() == "rejected":
        repro_readiness = "blocked_by_rejected_evidence_plan"
    return {
        "schema": "pointer_gpf.v2.repro_flow_plan.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": assertion_set.get("bug_summary", ""),
        "strategy": strategy,
        "base_flow": {
            "source": str(flow_file) if strategy == "reuse_project_basicflow" else "",
            "exists": strategy == "reuse_project_basicflow",
        },
        "assertion_set": assertion_set,
        "planned_assertion_step_count": planned_step_count,
        "unsupported_assertions": unsupported_assertions,
        "assertion_coverage": assertion_coverage,
        "model_evidence_plan_status": str(evidence_plan_payload.get("status", "")).strip(),
        "model_evidence_plan": evidence_plan_payload.get("plan", {}) if isinstance(evidence_plan_payload.get("plan", {}), dict) else {},
        "rejected_evidence_plan_reasons": evidence_plan_payload.get("rejected_reasons", []) if isinstance(evidence_plan_payload.get("rejected_reasons", []), list) else [],
        "planned_runtime_evidence_step_count": len(model_evidence_steps),
        "model_planned_step_ids": [str(step.get("id", "")).strip() for step in model_evidence_steps if str(step.get("id", "")).strip()],
        "evidence_step_coverage": _model_step_coverage(model_evidence_steps),
        "evidence_refs_required": evidence_refs_required,
        "evidence_refs_produced": evidence_refs_produced,
        "needs_flow_patch": bool(planned_step_count or model_evidence_steps),
        "repro_readiness": repro_readiness,
        "candidate_flow": candidate_flow,
        "execution_contract": _build_execution_contract(candidate_steps),
        "next_action": "review_or_materialize_repro_flow",
    }
