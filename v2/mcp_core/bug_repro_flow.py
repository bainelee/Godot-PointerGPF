from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .basicflow_assets import BasicFlowAssetError, basicflow_paths, load_basicflow_assets
from .bug_assertions import define_bug_assertions


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
            if action in {"wait", "check"}:
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


def plan_bug_repro_flow(project_root: Path, args: Any) -> dict[str, Any]:
    assertion_set = define_bug_assertions(project_root, args)
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
        candidate_core = core_steps + planned_precondition_steps + planned_postcondition_steps
    else:
        trigger_insert_index = _find_first_trigger_index(core_steps)
        if trigger_insert_index is None:
            candidate_core = core_steps + planned_precondition_steps
            if planned_trigger is not None:
                candidate_core.append(planned_trigger)
            candidate_core.extend(planned_postcondition_steps)
        else:
            candidate_core = (
                core_steps[:trigger_insert_index]
                + planned_precondition_steps
                + core_steps[trigger_insert_index:]
                + planned_postcondition_steps
            )

    candidate_steps = candidate_core + close_steps
    flow_file = basicflow_paths(project_root).flow_file
    candidate_flow = {
        "flowId": "planned_bug_repro_flow",
        "name": "Planned Bug Repro Flow",
        "description": f"Planned repro flow for: {assertion_set.get('bug_summary', '')}",
        "steps": candidate_steps,
    }

    planned_step_count = len(planned_precondition_steps) + len(planned_postcondition_steps) + (1 if planned_trigger is not None else 0)
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
        "needs_flow_patch": bool(planned_step_count),
        "repro_readiness": "blocked_by_unsupported_assertions" if unsupported_assertions else "ready_for_repro_run",
        "candidate_flow": candidate_flow,
        "execution_contract": _build_execution_contract(candidate_steps),
        "next_action": "review_or_materialize_repro_flow",
    }
