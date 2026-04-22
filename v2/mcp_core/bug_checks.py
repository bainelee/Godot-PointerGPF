from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .bug_assertions import define_bug_assertions
from .bug_repro_flow import plan_bug_repro_flow


def _runtime_hint_for_step(step: dict[str, Any]) -> str:
    if isinstance(step.get("until"), dict):
        hint = str(step["until"].get("hint", "")).strip()
        if hint:
            return hint
    hint = str(step.get("hint", "")).strip()
    if hint:
        return hint
    target = step.get("target", {})
    if isinstance(target, dict):
        return str(target.get("hint", "")).strip()
    return ""


def _runtime_action_for_step(step: dict[str, Any]) -> str:
    return str(step.get("action", "")).strip().lower()


def _compile_assertion_check(assertion: dict[str, Any], *, stage: str, index: int) -> dict[str, Any] | None:
    runtime_check = assertion.get("runtime_check", {})
    if not isinstance(runtime_check, dict) or not bool(runtime_check.get("supported", False)):
        return None
    hint = str(runtime_check.get("hint", "")).strip()
    if not hint:
        return None
    action = str(runtime_check.get("action", "check")).strip() or "check"
    target = assertion.get("target", {})
    if not isinstance(target, dict):
        target = {}
    return {
        "check_id": f"{stage}_check_{index}_{str(assertion.get('id', 'runtime_check')).strip() or 'runtime_check'}",
        "source_assertion_id": str(assertion.get("id", "")).strip(),
        "stage": stage,
        "kind": str(assertion.get("kind", "")).strip(),
        "action": action,
        "hint": hint,
        "target": target,
        "reason": str(assertion.get("reason", "")).strip(),
        "expected": assertion.get("expected", True),
        "mapped_step_id": "",
        "mapped_step_action": "",
    }


def build_executable_checks(assertion_set: dict[str, Any], candidate_flow: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for index, assertion in enumerate(assertion_set.get("preconditions", [])):
        if not isinstance(assertion, dict):
            continue
        compiled = _compile_assertion_check(assertion, stage="precondition", index=index)
        if compiled is not None:
            checks.append(compiled)
    for index, assertion in enumerate(assertion_set.get("postconditions", [])):
        if not isinstance(assertion, dict):
            continue
        compiled = _compile_assertion_check(assertion, stage="postcondition", index=index)
        if compiled is not None:
            checks.append(compiled)

    if not isinstance(candidate_flow, dict):
        return checks

    steps = candidate_flow.get("steps", [])
    if not isinstance(steps, list):
        return checks

    step_candidates: list[dict[str, str]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_candidates.append(
            {
                "id": str(step.get("id", "")).strip(),
                "action": _runtime_action_for_step(step),
                "hint": _runtime_hint_for_step(step),
            }
        )

    for check in checks:
        for step in step_candidates:
            if step["action"] != str(check.get("action", "")).strip().lower():
                continue
            if step["hint"] != str(check.get("hint", "")).strip():
                continue
            check["mapped_step_id"] = step["id"]
            check["mapped_step_action"] = step["action"]
            break

    return checks


def summarize_check_results(
    candidate_flow: dict[str, Any],
    checks: list[dict[str, Any]],
    *,
    run_ok: bool,
    failed_step_id: str,
    failure_status: str,
    error_code: str,
    error_message: str,
) -> dict[str, Any]:
    steps = candidate_flow.get("steps", []) if isinstance(candidate_flow, dict) else []
    if not isinstance(steps, list):
        steps = []
    step_order = {
        str(step.get("id", "")).strip(): index
        for index, step in enumerate(steps)
        if isinstance(step, dict) and str(step.get("id", "")).strip()
    }
    failed_index = step_order.get(failed_step_id, -1)
    results: list[dict[str, Any]] = []
    passed_count = 0
    failed_count = 0
    not_run_count = 0
    unknown_count = 0

    for check in checks:
        mapped_step_id = str(check.get("mapped_step_id", "")).strip()
        status = "unknown"
        if run_ok:
            status = "passed"
        elif mapped_step_id and failed_index >= 0:
            current_index = step_order.get(mapped_step_id, -1)
            if current_index >= 0 and current_index < failed_index:
                status = "passed"
            elif current_index == failed_index:
                status = "failed"
            elif current_index > failed_index:
                status = "not_run"
        result = {
            **check,
            "status": status,
            "evidence": {
                "run_status": failure_status if not run_ok else "bug_not_reproduced",
                "failed_step_id": failed_step_id,
                "error_code": error_code,
                "error_message": error_message,
            },
        }
        results.append(result)
        if status == "passed":
            passed_count += 1
        elif status == "failed":
            failed_count += 1
        elif status == "not_run":
            not_run_count += 1
        else:
            unknown_count += 1

    failed_checks = [
        {
            "check_id": str(item.get("check_id", "")).strip(),
            "source_assertion_id": str(item.get("source_assertion_id", "")).strip(),
            "hint": str(item.get("hint", "")).strip(),
            "reason": str(item.get("reason", "")).strip(),
            "mapped_step_id": str(item.get("mapped_step_id", "")).strip(),
        }
        for item in results
        if str(item.get("status", "")).strip() == "failed"
    ]

    return {
        "results": results,
        "summary": {
            "total": len(results),
            "passed": passed_count,
            "failed": failed_count,
            "not_run": not_run_count,
            "unknown": unknown_count,
            "failed_check_ids": [item["check_id"] for item in failed_checks if item["check_id"]],
            "failed_assertion_ids": [item["source_assertion_id"] for item in failed_checks if item["source_assertion_id"]],
            "failed_checks": failed_checks[:5],
        },
    }


def define_bug_checks(
    project_root: Path,
    args: Any,
    *,
    define_bug_assertions_fn: Callable[[Path, Any], dict[str, Any]] = define_bug_assertions,
    plan_bug_repro_flow_fn: Callable[[Path, Any], dict[str, Any]] = plan_bug_repro_flow,
) -> dict[str, Any]:
    assertion_set = define_bug_assertions_fn(project_root, args)
    repro_plan = plan_bug_repro_flow_fn(project_root, args)
    candidate_flow = repro_plan.get("candidate_flow", {})
    checks = build_executable_checks(assertion_set, candidate_flow if isinstance(candidate_flow, dict) else {})
    return {
        "schema": "pointer_gpf.v2.check_set.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": assertion_set.get("bug_summary", ""),
        "assertion_set": assertion_set,
        "checks": checks,
    }
