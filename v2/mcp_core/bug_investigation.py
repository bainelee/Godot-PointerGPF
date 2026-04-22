from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .bug_checks import define_bug_checks
from .bug_observation import observe_bug_context
from .bug_repro_flow import plan_bug_repro_flow


def _runtime_action_groups(candidate_flow: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    steps = candidate_flow.get("steps", []) if isinstance(candidate_flow, dict) else []
    if not isinstance(steps, list):
        steps = []
    setup: list[dict[str, Any]] = []
    trigger: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    close: list[dict[str, Any]] = []
    seen_trigger = False
    for step in steps:
        if not isinstance(step, dict):
            continue
        hint = ""
        if isinstance(step.get("until"), dict):
            hint = str(step["until"].get("hint", "")).strip()
        if not hint:
            hint = str(step.get("hint", "")).strip()
        if not hint and isinstance(step.get("target"), dict):
            hint = str(step["target"].get("hint", "")).strip()
        normalized = {
            "step_id": str(step.get("id", "")).strip(),
            "action": str(step.get("action", "")).strip(),
            "hint": hint,
        }
        action = normalized["action"].lower()
        if action == "closeproject":
            close.append(normalized)
        elif action == "click":
            trigger.append(normalized)
            seen_trigger = True
        elif not seen_trigger:
            setup.append(normalized)
        else:
            checks.append(normalized)
    return {
        "setup": setup,
        "trigger": trigger,
        "checks": checks,
        "close": close,
    }


def _check_candidates(assertion_set: dict[str, Any]) -> list[dict[str, Any]]:
    assertions = assertion_set.get("assertions", [])
    if not isinstance(assertions, list):
        assertions = []
    checks: list[dict[str, Any]] = []
    for assertion in assertions:
        if not isinstance(assertion, dict):
            continue
        runtime_check = assertion.get("runtime_check", {})
        if not isinstance(runtime_check, dict) or not bool(runtime_check.get("supported", False)):
            continue
        checks.append(
            {
                "assertion_id": str(assertion.get("id", "")).strip(),
                "kind": str(assertion.get("kind", "")).strip(),
                "hint": str(runtime_check.get("hint", "")).strip(),
                "action": str(runtime_check.get("action", "check")).strip() or "check",
                "reason": str(assertion.get("reason", "")).strip(),
            }
        )
    return checks[:12]


def _failure_branches(observation: dict[str, Any], repro_plan: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = observation.get("bug_analysis", {})
    scripts = []
    scenes = []
    if isinstance(analysis, dict):
        artifacts = analysis.get("affected_artifacts", {})
        if isinstance(artifacts, dict):
            scripts = [str(item).strip() for item in artifacts.get("scripts", []) if str(item).strip()]
            scenes = [str(item).strip() for item in artifacts.get("scenes", []) if str(item).strip()]
    location_hint = observation.get("bug_intake", {}).get("location_hint", {}) if isinstance(observation.get("bug_intake", {}), dict) else {}
    node_name = str(location_hint.get("node", "")).strip() if isinstance(location_hint, dict) else ""
    branches = [
        {
            "when": "precondition_failed",
            "goal": "confirm whether the bug path was never reached or the interaction target is missing too early",
            "actions": [
                "inspect the startup scene and related scene files first",
                "inspect the runtime hints that should prove the interaction target exists",
            ],
            "primary_files": scenes[:2] + scripts[:1],
        },
        {
            "when": "trigger_failed",
            "goal": "confirm whether the intended input path is wrong or the trigger is bound to the wrong node/callback",
            "actions": [
                f"inspect the trigger node path for {node_name}" if node_name else "inspect the trigger node path",
                "inspect related callback or signal-binding scripts",
            ],
            "primary_files": scripts[:2] + scenes[:1],
        },
        {
            "when": "runtime_invalid",
            "goal": "inspect runtime diagnostics before deciding whether the issue is gameplay logic or engine/runtime failure",
            "actions": [
                "read runtime diagnostics and the latest failed step id",
                "separate engine/runtime failure from gameplay-state failure",
            ],
            "primary_files": scripts[:2],
        },
        {
            "when": "bug_not_reproduced",
            "goal": "strengthen the operation path or checks if current evidence is too weak to expose the bug",
            "actions": [
                "compare planned checks against expected non-bug assertions",
                "tighten the trigger step or add a more direct post-trigger check",
            ],
            "primary_files": scenes[:1] + scripts[:2],
        },
    ]
    return branches


def _repair_focus(observation: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = observation.get("bug_analysis", {})
    causes = analysis.get("suspected_causes", []) if isinstance(analysis, dict) else []
    files = observation.get("candidate_file_read_order", [])
    if not isinstance(files, list):
        files = []
    focus: list[dict[str, Any]] = []
    for cause in causes:
        if not isinstance(cause, dict):
            continue
        focus.append(
            {
                "cause_kind": str(cause.get("kind", "")).strip(),
                "reason": str(cause.get("reason", "")).strip(),
                "candidate_files": files[:3],
            }
        )
    return focus[:5]


def plan_bug_investigation(
    project_root: Path,
    args: Any,
    *,
    observe_bug_context_fn: Callable[[Path, Any], dict[str, Any]] = observe_bug_context,
    plan_bug_repro_flow_fn: Callable[[Path, Any], dict[str, Any]] = plan_bug_repro_flow,
    define_bug_checks_fn: Callable[[Path, Any], dict[str, Any]] = define_bug_checks,
) -> dict[str, Any]:
    observation = observe_bug_context_fn(project_root, args)
    repro_plan = plan_bug_repro_flow_fn(project_root, args)
    check_set = define_bug_checks_fn(project_root, args)
    candidate_flow = repro_plan.get("candidate_flow", {})
    runtime_actions = _runtime_action_groups(candidate_flow if isinstance(candidate_flow, dict) else {})
    checks = _check_candidates(observation.get("assertion_set", {}))
    return {
        "schema": "pointer_gpf.v2.bug_investigation_plan.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": observation.get("bug_summary", ""),
        "round_id": str(observation.get("bug_intake", {}).get("round_id", "")).strip()
        if isinstance(observation.get("bug_intake", {}), dict)
        else "",
        "bug_id": str(observation.get("bug_intake", {}).get("bug_id", "")).strip()
        if isinstance(observation.get("bug_intake", {}), dict)
        else "",
        "bug_source": str(observation.get("bug_intake", {}).get("bug_source", "pre_existing")).strip()
        if isinstance(observation.get("bug_intake", {}), dict)
        else "pre_existing",
        "observation": observation,
        "candidate_file_read_order": observation.get("candidate_file_read_order", []),
        "runtime_action_groups": runtime_actions,
        "executable_check_set": check_set,
        "check_candidates": checks,
        "failure_branches": _failure_branches(observation, repro_plan),
        "repair_focus": _repair_focus(observation),
        "recommended_next_tools": [
            "define_bug_checks",
            "run_bug_repro_flow",
            "plan_bug_fix",
            "verify_bug_fix",
        ],
        "recommended_next_action": "run_bug_repro_flow",
    }
