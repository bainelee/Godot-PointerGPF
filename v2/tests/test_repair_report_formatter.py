import unittest

from v2.mcp_core.repair_report_formatter import format_repair_report


class RepairReportFormatterTests(unittest.TestCase):
    def test_format_repair_report_maps_summary_to_artifacts(self) -> None:
        payload = {
            "status": "fixed_and_verified",
            "bug_summary": "敌人受击后没有闪红",
            "repair_summary": {
                "schema": "pointer_gpf.v2.repair_summary.v1",
                "status": "fixed_and_verified",
                "bug_summary": "敌人受击后没有闪红",
                "bug_source": "injected",
                "injected_bug_kind": "hit_feedback_shader_not_updated",
                "round_id": "round-1",
                "bug_id": "bug-1",
                "repro": {
                    "status": "bug_reproduced",
                    "failed_phase": "postcondition",
                    "failed_check_ids": ["check_enemy_hit_count_after_one"],
                    "runtime_evidence_ids": ["enemy_hit_count_after"],
                    "artifact_file": "repro.json",
                },
                "fix_plan": {
                    "status": "fix_ready",
                    "candidate_files": [{"path": "res://scripts/enemies/test_enemy.gd"}],
                    "fix_goals": [{"goal": "sync shader hit_count"}],
                },
                "apply": {
                    "status": "fix_applied",
                    "applied_changes": [{"path": "res://scripts/enemies/test_enemy.gd"}],
                    "proposal_artifact": "proposal.json",
                    "application_artifact": "apply.json",
                },
                "rerun": {
                    "status": "bug_not_reproduced",
                    "runtime_evidence_ids": ["enemy_hit_count_after"],
                    "artifact_file": "rerun.json",
                },
                "regression": {
                    "status": "passed",
                    "artifact_file": "regression.json",
                },
            },
            "artifact_summary": {
                "files": ["repro.json", "proposal.json", "apply.json", "rerun.json", "regression.json"],
                "by_stage": {
                    "repro_artifact": "repro.json",
                    "proposal_artifact": "proposal.json",
                    "application_artifact": "apply.json",
                    "rerun_artifact": "rerun.json",
                    "regression_artifact": "regression.json",
                },
            },
        }

        report = format_repair_report(payload)

        self.assertEqual(report["schema"], "pointer_gpf.v2.user_repair_report.v1")
        self.assertEqual(report["status"], "fixed_and_verified")
        self.assertEqual(report["sections"]["bug"]["source"], "injected (hit_feedback_shader_not_updated)")
        self.assertEqual(report["sections"]["repro"]["artifact"], "repro.json")
        self.assertEqual(report["sections"]["fix"]["changed_files"], ["res://scripts/enemies/test_enemy.gd"])
        self.assertEqual(report["sections"]["verification"]["regression_artifact"], "regression.json")
        self.assertIn("Repair status: fixed_and_verified", report["markdown"])
        self.assertIn("artifact: repro.json", report["markdown"])
        self.assertIn("artifact: regression.json", report["markdown"])


if __name__ == "__main__":
    unittest.main()
