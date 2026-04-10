"""Unit tests for gameplay_runnability vs execution_report evidence."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

from basic_flow_contracts import build_dual_conclusions  # noqa: E402


def _strong_runtime_report() -> dict:
    return {
        "status": "passed",
        "step_count": 2,
        "runtime_mode": "play_mode",
        "runtime_entry": "already_running_play_session",
        "runtime_gate_passed": True,
        "input_mode": "in_engine_virtual_input",
        "os_input_interference": False,
        "phase_coverage": {"started": 2, "result": 2, "verify": 2},
        "step_broadcast_summary": {"protocol_mode": "three_phase", "fail_fast_on_verify": True},
    }


class BasicFlowDualConclusionsTests(unittest.TestCase):
    def test_gameplay_fails_when_only_one_step_despite_runtime_ok(self) -> None:
        rep = _strong_runtime_report()
        rep["step_count"] = 1
        dual = build_dual_conclusions(rep)
        self.assertFalse(dual["gameplay_runnability"]["passed"])
        self.assertTrue(dual["tool_usability"]["passed"])

    def test_gameplay_fails_when_protocol_mode_not_three_phase(self) -> None:
        rep = _strong_runtime_report()
        rep["step_broadcast_summary"] = {"protocol_mode": "other", "fail_fast_on_verify": True}
        dual = build_dual_conclusions(rep)
        self.assertFalse(dual["gameplay_runnability"]["passed"])

    def test_gameplay_fails_when_fail_fast_not_true(self) -> None:
        rep = _strong_runtime_report()
        rep["step_broadcast_summary"] = {"protocol_mode": "three_phase", "fail_fast_on_verify": False}
        dual = build_dual_conclusions(rep)
        self.assertFalse(dual["gameplay_runnability"]["passed"])

    def test_gameplay_passes_with_full_evidence(self) -> None:
        dual = build_dual_conclusions(_strong_runtime_report())
        self.assertTrue(dual["gameplay_runnability"]["passed"])
        ev = dual["gameplay_runnability"]["evidence"]
        self.assertEqual(ev["step_broadcast_summary"]["protocol_mode"], "three_phase")
        self.assertEqual(ev["phase_coverage"]["verify"], 2)


if __name__ == "__main__":
    unittest.main()
