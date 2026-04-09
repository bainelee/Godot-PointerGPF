"""基础测试流程对外契约：双结论（工具可用性 / 玩法可运行性）由 execution_report 推导。"""

from __future__ import annotations

from typing import Any


def _tool_usability_from_execution_report(execution_report: dict[str, Any]) -> dict[str, Any]:
    step_count = int(execution_report.get("step_count") or 0)
    st = str(execution_report.get("status", ""))
    cov_raw = execution_report.get("phase_coverage") if isinstance(execution_report.get("phase_coverage"), dict) else {}
    started = int(cov_raw.get("started") or 0)
    result_n = int(cov_raw.get("result") or 0)
    verify_n = int(cov_raw.get("verify") or 0)
    passed = (
        step_count >= 1
        and st == "passed"
        and started >= 1
        and result_n >= 1
        and verify_n >= 1
    )
    return {
        "passed": passed,
        "evidence": {
            "status": st,
            "step_count": step_count,
            "phase_coverage": {"started": started, "result": result_n, "verify": verify_n},
        },
    }


def _gameplay_runnability_from_execution_report(execution_report: dict[str, Any]) -> dict[str, Any]:
    st = str(execution_report.get("status", ""))
    step_count = int(execution_report.get("step_count") or 0)
    return {
        "passed": st == "passed",
        "evidence": {
            "status": st,
            "step_count": step_count,
        },
    }


def build_dual_conclusions(execution_report: dict[str, Any]) -> dict[str, Any]:
    rep = execution_report if isinstance(execution_report, dict) else {}
    return {
        "tool_usability": _tool_usability_from_execution_report(rep),
        "gameplay_runnability": _gameplay_runnability_from_execution_report(rep),
    }
