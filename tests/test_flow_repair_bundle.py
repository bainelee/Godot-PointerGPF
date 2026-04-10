"""Unit tests for mcp.flow_repair_bundle."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import flow_repair_bundle  # noqa: E402


class TestFlowRepairBundle(unittest.TestCase):
    def test_auto_repair_disabled_only_runs_flow_fn(self) -> None:
        calls: list[str] = []

        def fake_flow() -> dict:
            calls.append("flow")
            return {"execution_result": {"status": "failed"}}

        def fake_repair(kwargs: dict) -> dict:
            calls.append("repair")
            return {}

        out = flow_repair_bundle.run_flow_once_and_maybe_repair(
            project_root=Path("."),
            auto_repair_enabled=False,
            max_repair_rounds=2,
            auto_fix_max_cycles=3,
            run_flow_bundle=fake_flow,
            run_auto_fix_bundle=fake_repair,
            build_issue_from_failure=lambda r: "x",
        )
        self.assertEqual(calls, ["flow"])
        self.assertEqual(out["final_status"], "failed_without_repair")

    def test_auto_repair_enabled_calls_repair_when_failed(self) -> None:
        calls: list[str] = []

        def fake_flow() -> dict:
            calls.append("flow")
            return {"execution_result": {"status": "failed"}}

        def fake_repair(kwargs: dict) -> dict:
            calls.append("repair")
            return {"final_status": "exhausted", "cycles_completed": 1, "loop_evidence": []}

        out = flow_repair_bundle.run_flow_once_and_maybe_repair(
            project_root=Path("."),
            auto_repair_enabled=True,
            max_repair_rounds=1,
            auto_fix_max_cycles=1,
            run_flow_bundle=fake_flow,
            run_auto_fix_bundle=fake_repair,
            build_issue_from_failure=lambda r: "step failed",
        )
        self.assertEqual(calls, ["flow", "repair"])
        self.assertIn("repair_rounds", out)
