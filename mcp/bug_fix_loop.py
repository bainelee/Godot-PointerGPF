"""Bug-fix loop: verify -> diagnose -> patch -> retest, with max_cycles and wall-clock timeout."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from bug_fix_strategies import run_apply_patch, run_diagnosis
from failure_taxonomy import FailureSignal, classify_failure

if TYPE_CHECKING:
    from remediation_trace import RemediationTrace

VerificationFn = Callable[[], dict[str, Any]]
MonotonicFn = Callable[[], float]
L2TryPatchFn = Callable[[Path, str, dict[str, Any], dict[str, Any]], dict[str, Any]]


def _remediation_class_from_verification(verification: dict[str, Any]) -> str:
    ae = verification.get("app_error")
    code: str | None = None
    if isinstance(ae, dict):
        raw = ae.get("code")
        if raw is not None and str(raw).strip():
            code = str(raw)
    status = str(verification.get("status", "")).strip().lower()
    return classify_failure(FailureSignal(code, status if status else None, None))


def _empty_trace_json() -> dict[str, Any]:
    return {"run_id": "", "events": []}


def run_bug_fix_loop(
    *,
    project_root: Path,
    issue: str,
    max_cycles: int,
    timeout_seconds: float | None,
    run_verification: VerificationFn,
    monotonic: MonotonicFn | None = None,
    l2_try_patch: L2TryPatchFn | None = None,
    trace: RemediationTrace | None = None,
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
            "remediation_trace": trace.to_json() if trace is not None else _empty_trace_json(),
        }

    verification0 = run_verification()
    if trace is not None:
        trace.append(
            "verify",
            {"passed": bool(verification0.get("passed")), "status": verification0.get("status")},
        )
    if bool(verification0.get("passed")):
        return {
            "final_status": "fixed",
            "cycles_completed": 0,
            "loop_evidence": [],
            "issue": str(issue or "").strip(),
            "project_root": str(project_root.resolve()),
            "initial_verification": verification0,
            "remediation_trace": trace.to_json() if trace is not None else _empty_trace_json(),
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
                "remediation_trace": trace.to_json() if trace is not None else _empty_trace_json(),
            }

        if cycle_index > 1:
            verification = run_verification()
            if trace is not None:
                trace.append(
                    "verify",
                    {"passed": bool(verification.get("passed")), "status": verification.get("status")},
                )
            if bool(verification.get("passed")):
                return {
                    "final_status": "fixed",
                    "cycles_completed": len(loop_evidence),
                    "loop_evidence": loop_evidence,
                    "issue": str(issue or "").strip(),
                    "project_root": str(project_root.resolve()),
                    "remediation_trace": trace.to_json() if trace is not None else _empty_trace_json(),
                }

        diagnosis = run_diagnosis(str(issue), verification)
        if trace is not None:
            trace.append("locate", {"diagnosis": diagnosis})

        patch = run_apply_patch(
            project_root.resolve(),
            str(issue),
            diagnosis,
            verification=verification,
        )
        if not bool(patch.get("applied")) and l2_try_patch is not None:
            try:
                l2_patch = l2_try_patch(project_root.resolve(), str(issue), diagnosis, verification)
            except Exception as exc:  # noqa: BLE001 — L2 is third-party hook; keep loop stable
                l2_patch = {"applied": False, "changed_files": [], "notes": str(exc)}
            if isinstance(l2_patch, dict) and bool(l2_patch.get("applied")):
                patch = l2_patch
            elif isinstance(l2_patch, dict):
                patch = {**patch, "l2_attempt": l2_patch}

        if trace is not None:
            trace.append("patch", dict(patch))

        if timed_out():
            ev_timeout = {
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
                "remediation_class": _remediation_class_from_verification(verification),
            }
            loop_evidence.append(ev_timeout)
            if trace is not None:
                trace.append(
                    "retest",
                    {"passed": False, "status": "timeout", "skipped": True},
                )
            return {
                "final_status": "timeout",
                "cycles_completed": len(loop_evidence),
                "loop_evidence": loop_evidence,
                "issue": str(issue or "").strip(),
                "project_root": str(project_root.resolve()),
                "remediation_trace": trace.to_json() if trace is not None else _empty_trace_json(),
            }

        retest = run_verification()
        if trace is not None:
            trace.append(
                "retest",
                {"passed": bool(retest.get("passed")), "status": retest.get("status")},
            )
        loop_evidence.append(
            {
                "cycle_index": cycle_index,
                "verification": verification,
                "diagnosis": diagnosis,
                "patch": patch,
                "retest": retest,
                "remediation_class": _remediation_class_from_verification(verification),
            }
        )

        if bool(retest.get("passed")):
            return {
                "final_status": "fixed",
                "cycles_completed": len(loop_evidence),
                "loop_evidence": loop_evidence,
                "issue": str(issue or "").strip(),
                "project_root": str(project_root.resolve()),
                "remediation_trace": trace.to_json() if trace is not None else _empty_trace_json(),
            }

    return {
        "final_status": "not_fixed",
        "cycles_completed": len(loop_evidence),
        "loop_evidence": loop_evidence,
        "issue": str(issue or "").strip(),
        "project_root": str(project_root.resolve()),
        "remediation_trace": trace.to_json() if trace is not None else _empty_trace_json(),
    }
