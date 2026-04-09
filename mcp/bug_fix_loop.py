"""Bug-fix loop: verify -> diagnose -> patch -> retest, with max_cycles and wall-clock timeout."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from bug_fix_strategies import run_apply_patch, run_diagnosis

VerificationFn = Callable[[], dict[str, Any]]
MonotonicFn = Callable[[], float]


def run_bug_fix_loop(
    *,
    project_root: Path,
    issue: str,
    max_cycles: int,
    timeout_seconds: float | None,
    run_verification: VerificationFn,
    monotonic: MonotonicFn | None = None,
) -> dict[str, Any]:
    mono = monotonic if monotonic is not None else time.monotonic
    deadline: float | None = None
    if timeout_seconds is not None:
        if timeout_seconds <= 0:
            deadline = mono()
        else:
            deadline = mono() + float(timeout_seconds)

    def timed_out() -> bool:
        return deadline is not None and mono() >= deadline

    loop_evidence: list[dict[str, Any]] = []

    if timed_out():
        return {
            "final_status": "timeout",
            "cycles_completed": 0,
            "loop_evidence": [],
            "issue": str(issue or "").strip(),
            "project_root": str(project_root.resolve()),
        }

    verification0 = run_verification()
    if bool(verification0.get("passed")):
        return {
            "final_status": "fixed",
            "cycles_completed": 0,
            "loop_evidence": [],
            "issue": str(issue or "").strip(),
            "project_root": str(project_root.resolve()),
            "initial_verification": verification0,
        }

    cycles = max(0, int(max_cycles))
    verification = verification0

    for cycle_index in range(1, cycles + 1):
        if timed_out():
            return {
                "final_status": "timeout",
                "cycles_completed": len(loop_evidence),
                "loop_evidence": loop_evidence,
                "issue": str(issue or "").strip(),
                "project_root": str(project_root.resolve()),
            }

        if cycle_index > 1:
            verification = run_verification()
            if bool(verification.get("passed")):
                return {
                    "final_status": "fixed",
                    "cycles_completed": len(loop_evidence),
                    "loop_evidence": loop_evidence,
                    "issue": str(issue or "").strip(),
                    "project_root": str(project_root.resolve()),
                }

        diagnosis = run_diagnosis(str(issue), verification)
        patch = run_apply_patch(project_root.resolve(), str(issue), diagnosis)

        if timed_out():
            loop_evidence.append(
                {
                    "cycle_index": cycle_index,
                    "verification": verification,
                    "diagnosis": diagnosis,
                    "patch": patch,
                    "retest": {
                        "passed": False,
                        "status": "timeout",
                        "skipped": True,
                        "note": "在复测前已超过 timeout_seconds。",
                    },
                }
            )
            return {
                "final_status": "timeout",
                "cycles_completed": len(loop_evidence),
                "loop_evidence": loop_evidence,
                "issue": str(issue or "").strip(),
                "project_root": str(project_root.resolve()),
            }

        retest = run_verification()
        loop_evidence.append(
            {
                "cycle_index": cycle_index,
                "verification": verification,
                "diagnosis": diagnosis,
                "patch": patch,
                "retest": retest,
            }
        )

        if bool(retest.get("passed")):
            return {
                "final_status": "fixed",
                "cycles_completed": len(loop_evidence),
                "loop_evidence": loop_evidence,
                "issue": str(issue or "").strip(),
                "project_root": str(project_root.resolve()),
            }

    return {
        "final_status": "not_fixed",
        "cycles_completed": len(loop_evidence),
        "loop_evidence": loop_evidence,
        "issue": str(issue or "").strip(),
        "project_root": str(project_root.resolve()),
    }
