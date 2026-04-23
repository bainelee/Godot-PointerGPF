import argparse
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_repair_workflow import repair_reported_bug


class BugRepairWorkflowTests(unittest.TestCase):
    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            bug_report="敌人受击后没有闪红",
            expected_behavior="敌人受击后应该闪红一次",
            evidence_plan_json="",
            evidence_plan_file="",
            fix_proposal_json="",
            fix_proposal_file="",
        )

    def test_repair_reported_bug_waits_for_model_evidence_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = repair_reported_bug(
                Path(tmp),
                self._args(),
                collect_bug_report_fn=lambda *_: {"summary": "敌人受击后没有闪红"},
                observe_bug_context_fn=lambda *_: {"status": "observed"},
                plan_bug_repro_flow_fn=lambda *_: {"model_evidence_plan_status": "not_provided"},
                run_bug_repro_flow_fn=lambda *_: {},
                plan_bug_fix_fn=lambda *_: {},
                apply_bug_fix_fn=lambda *_: {},
                rerun_bug_repro_flow_fn=lambda *_: {},
                run_bug_fix_regression_fn=lambda *_: {},
            )

        self.assertEqual(payload["status"], "awaiting_model_evidence_plan")
        self.assertEqual(payload["next_action"], "provide_evidence_plan_json_or_file")

    def test_repair_reported_bug_waits_for_fix_proposal_after_repro_and_fix_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = repair_reported_bug(
                Path(tmp),
                self._args(),
                collect_bug_report_fn=lambda *_: {"summary": "敌人受击后没有闪红"},
                observe_bug_context_fn=lambda *_: {"status": "observed"},
                plan_bug_repro_flow_fn=lambda *_: {"model_evidence_plan_status": "accepted"},
                run_bug_repro_flow_fn=lambda *_: {"status": "bug_reproduced", "artifact_file": "repro.json"},
                plan_bug_fix_fn=lambda *_: {"status": "fix_ready"},
                apply_bug_fix_fn=lambda *_: {},
                rerun_bug_repro_flow_fn=lambda *_: {},
                run_bug_fix_regression_fn=lambda *_: {},
            )

        self.assertEqual(payload["status"], "bug_reproduced_awaiting_fix_proposal")
        self.assertEqual(payload["next_action"], "provide_fix_proposal_json_or_file")

    def test_repair_reported_bug_reports_fixed_and_verified(self) -> None:
        args = self._args()
        args.fix_proposal_json = '{"candidate_file":"res://scripts/enemy.gd","edits":[]}'
        with tempfile.TemporaryDirectory() as tmp:
            payload = repair_reported_bug(
                Path(tmp),
                args,
                collect_bug_report_fn=lambda *_: {"summary": "敌人受击后没有闪红"},
                observe_bug_context_fn=lambda *_: {"status": "observed"},
                plan_bug_repro_flow_fn=lambda *_: {"model_evidence_plan_status": "accepted"},
                run_bug_repro_flow_fn=lambda *_: {"status": "bug_reproduced", "artifact_file": "repro.json"},
                plan_bug_fix_fn=lambda *_: {"status": "fix_ready"},
                apply_bug_fix_fn=lambda *_: {
                    "status": "fix_applied",
                    "applied_changes": [{"path": "res://scripts/enemy.gd"}],
                    "application_artifact": "apply.json",
                },
                rerun_bug_repro_flow_fn=lambda *_: {"status": "bug_not_reproduced", "artifact_file": "rerun.json"},
                run_bug_fix_regression_fn=lambda *_: {"status": "passed", "artifact_file": "regression.json"},
            )

        self.assertEqual(payload["status"], "fixed_and_verified")
        self.assertEqual(payload["next_action"], "")
        self.assertIn("repro.json", payload["artifact_files"])


if __name__ == "__main__":
    unittest.main()
