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

    return {
        "schema": "pointer_gpf.v2.repro_run.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": plan_payload.get("bug_summary", ""),
        "status": status,
        "reproduction_confirmed": reproduction_confirmed,
        "execution_mode": execution_mode,
        "flow_file": str(flow_file),
        "repro_flow_plan": plan_payload,
        "raw_run_result": raw_payload,
        "run_exit_code": exit_code,
        "blocking_point": str(error.get("message", "")).strip() if status == "flow_invalid" else "",
        "next_action": "inspect_failure_before_fixing" if status == "bug_reproduced" else "refine_repro_flow",
    }
