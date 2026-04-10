"""Unified flow run + optional auto-repair bundle (minimal single-round implementation)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

RunFlowFn = Callable[[], dict[str, Any]]
AutoFixFn = Callable[[dict[str, Any]], dict[str, Any]]
IssueFn = Callable[[dict[str, Any]], str]


def run_flow_once_and_maybe_repair(
    *,
    project_root: Path,
    auto_repair_enabled: bool,
    max_repair_rounds: int,
    auto_fix_max_cycles: int,
    run_flow_bundle: RunFlowFn,
    run_auto_fix_bundle: AutoFixFn,
    build_issue_from_failure: IssueFn,
    extra_auto_fix_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the flow once; on failure, optionally invoke a single auto-fix round.

    ``max_repair_rounds`` is reserved for forward-compatible multi-round repair;
    this minimal implementation does not loop on it (only one repair attempt when enabled).
    """
    bundle = run_flow_bundle()
    er = bundle.get("execution_result") if isinstance(bundle.get("execution_result"), dict) else {}
    if str(er.get("status", "")).strip() == "passed":
        return {"final_status": "passed", "flow_bundle": bundle, "repair_rounds": []}

    if not auto_repair_enabled:
        return {
            "final_status": "failed_without_repair",
            "flow_bundle": bundle,
            "repair_rounds": [],
        }

    issue = build_issue_from_failure(bundle)
    base: dict[str, Any] = {
        "project_root": str(project_root.resolve()),
        "issue": issue,
        "max_cycles": auto_fix_max_cycles,
    }
    if extra_auto_fix_args:
        base.update(extra_auto_fix_args)
    repair_payload = run_auto_fix_bundle(base)
    return {
        "final_status": "repaired_attempted",
        "flow_bundle": bundle,
        "repair_rounds": [{"round_index": 1, "auto_fix": repair_payload}],
    }
