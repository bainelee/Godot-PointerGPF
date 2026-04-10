"""Tests for remediation_trace integration in run_bug_fix_loop."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import bug_fix_loop  # noqa: E402
from remediation_trace import RemediationTrace  # noqa: E402


class TestBugFixLoopTrace(unittest.TestCase):
    @mock.patch("bug_fix_loop.run_apply_patch")
    @mock.patch("bug_fix_loop.run_diagnosis")
    def test_remediation_trace_records_four_phases(
        self, mock_diag: mock.MagicMock, mock_patch: mock.MagicMock
    ) -> None:
        mock_diag.return_value = {"strategy_id": "generic", "summary": "x"}
        mock_patch.return_value = {"applied": True, "changed_files": []}

        n = {"c": 0}

        def verify() -> dict:
            n["c"] += 1
            passed = n["c"] >= 2
            return {
                "passed": passed,
                "status": "passed" if passed else "failed",
                "app_error": None,
            }

        trace = RemediationTrace(run_id="t-loop")
        out = bug_fix_loop.run_bug_fix_loop(
            project_root=Path("."),
            issue="btn",
            max_cycles=1,
            timeout_seconds=None,
            run_verification=verify,
            trace=trace,
        )
        self.assertEqual(out["final_status"], "fixed")
        rt_json = out.get("remediation_trace")
        self.assertIsInstance(rt_json, dict)
        kinds = [e["kind"] for e in rt_json["events"]]
        self.assertIn("verify", kinds)
        self.assertIn("locate", kinds)
        self.assertIn("patch", kinds)
        self.assertIn("retest", kinds)


if __name__ == "__main__":
    unittest.main()
