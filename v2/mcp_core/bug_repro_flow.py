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
    flow_payload = deepcopy(assets.get("flow", {}))
    return flow_payload, "reuse_project_basicflow"


def _find_close_index(steps: list[dict[str, Any]]) -> int:
    for index, step in enumerate(steps):
        if str(step.get("action", "")).strip().lower() == "closeproject":
            return index
    return len(steps)


def _existing_runtime_hints(steps: list[dict[str, Any]]) -> set[str]:
    hints: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        hint = ""
        if isinstance(step.get("until"), dict):
            hint = str(step["until"].get("hint", "")).strip()
        if not hint:
            hint = str(step.get("hint", "")).strip()
        if hint:
            hints.add(hint)
    return hints


def _assertion_step(assertion: dict[str, Any], index: int) -> dict[str, Any] | None:
    runtime_check = assertion.get("runtime_check", {})
    if not isinstance(runtime_check, dict) or not bool(runtime_check.get("supported", False)):
        return None
    hint = str(runtime_check.get("hint", "")).strip()
    if not hint:
        return None
    action = str(runtime_check.get("action", "check")).strip() or "check"
    step_id = f"assert_{index}_{assertion.get('id', 'runtime_check')}"
    if action == "wait":
        return {
            "id": step_id,
            "action": "wait",
            "until": {"hint": hint},
            "timeoutMs": 5000,
        }
    return {
        "id": step_id,
        "action": "check",
        "hint": hint,
    }


def _covered_by_existing_assertions(assertion: dict[str, Any], assertion_set: dict[str, Any]) -> dict[str, Any] | None:
    assertion_id = str(assertion.get("id", "")).strip()
    if assertion_id != "interaction_should_change_state":
        return None
    assertions = assertion_set.get("assertions", [])
    if not isinstance(assertions, list):
        return None
    supporting_ids: list[str] = []
    for item in assertions:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "")).strip()
        runtime_check = item.get("runtime_check", {})
        if item_id in {"target_scene_reached", "target_runtime_anchor_present", "bug_free_runtime_anchor_present"} and bool(
            isinstance(runtime_check, dict) and runtime_check.get("supported", False)
        ):
            supporting_ids.append(item_id)
    if not supporting_ids:
        return None
    return {
        "assertion_id": assertion_id,
        "status": "covered_by_related_assertions",
        "reason": "state transition is treated as indirectly covered because target-scene or runtime-anchor assertions already verify post-click state change",
        "supporting_assertions": supporting_ids,
    }


def plan_bug_repro_flow(project_root: Path, args: Any) -> dict[str, Any]:
    assertion_set = define_bug_assertions(project_root, args)
    base_flow, strategy = _load_base_flow(project_root)
    steps = [step for step in base_flow.get("steps", []) if isinstance(step, dict)]
    close_index = _find_close_index(steps)
    existing_hints = _existing_runtime_hints(steps)

    planned_assertion_steps: list[dict[str, Any]] = []
    unsupported_assertions: list[str] = []
    assertion_coverage: list[dict[str, Any]] = []
    for index, assertion in enumerate(assertion_set.get("assertions", [])):
        if not isinstance(assertion, dict):
            continue
        step = _assertion_step(assertion, index)
        if step is None:
            covered = _covered_by_existing_assertions(assertion, assertion_set)
            if covered is not None:
                assertion_coverage.append(covered)
            else:
                unsupported_assertions.append(str(assertion.get("id", f"assertion_{index}")))
            continue
        step_hint = str(step.get("hint", "")).strip()
        if not step_hint and isinstance(step.get("until"), dict):
            step_hint = str(step["until"].get("hint", "")).strip()
        if step_hint and step_hint in existing_hints:
            assertion_coverage.append(
                {
                    "assertion_id": str(assertion.get("id", f"assertion_{index}")),
                    "status": "already_covered_by_base_flow",
                    "reason": f"base flow already contains runtime hint {step_hint}",
                    "supporting_assertions": [],
                }
            )
            continue
        planned_assertion_steps.append(step)
        if step_hint:
            existing_hints.add(step_hint)
        assertion_coverage.append(
            {
                "assertion_id": str(assertion.get("id", f"assertion_{index}")),
                "status": "covered_by_planned_step",
                "reason": "repro planner added an explicit step for this assertion",
                "supporting_assertions": [],
            }
        )

    candidate_steps = steps[:close_index] + planned_assertion_steps + steps[close_index:]
    flow_file = basicflow_paths(project_root).flow_file
    candidate_flow = {
        "flowId": "planned_bug_repro_flow",
        "name": "Planned Bug Repro Flow",
        "description": f"Planned repro flow for: {assertion_set.get('bug_summary', '')}",
        "steps": candidate_steps,
    }
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
        "planned_assertion_step_count": len(planned_assertion_steps),
        "unsupported_assertions": unsupported_assertions,
        "assertion_coverage": assertion_coverage,
        "needs_flow_patch": bool(planned_assertion_steps),
        "repro_readiness": "blocked_by_unsupported_assertions" if unsupported_assertions else "ready_for_repro_run",
        "candidate_flow": candidate_flow,
        "next_action": "review_or_materialize_repro_flow",
    }
