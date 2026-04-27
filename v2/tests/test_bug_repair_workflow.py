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
        observation = {
            "status": "observed",
            "project_static_observation": {
                "candidate_files": [{"path": "res://scripts/enemies/test_enemy.gd"}],
                "behavior_methods": [{"method": "_on_bullet_hit"}],
                "scene_nodes": [{"name": "TestEnemy"}],
                "visual_state_surfaces": [{"kind": "shader_param", "param_name": "hit_count"}],
                "runtime_evidence_target_candidates": [{"target": {"hint": "node_name:Sprite3D"}}],
            },
            "runtime_evidence_capabilities": {"actions": ["sample", "check", "callMethod"]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = repair_reported_bug(
                Path(tmp),
                self._args(),
                collect_bug_report_fn=lambda *_: {"summary": "敌人受击后没有闪红"},
                observe_bug_context_fn=lambda *_: observation,
                plan_bug_repro_flow_fn=lambda *_: {
                    "model_evidence_plan_status": "not_provided",
                    "model_evidence_plan_rejected_reasons": [],
                },
                run_bug_repro_flow_fn=lambda *_: {},
                plan_bug_fix_fn=lambda *_: {},
                apply_bug_fix_fn=lambda *_: {},
                rerun_bug_repro_flow_fn=lambda *_: {},
                run_bug_fix_regression_fn=lambda *_: {},
            )

        self.assertEqual(payload["status"], "awaiting_model_evidence_plan")
        self.assertEqual(payload["next_action"], "provide_evidence_plan_json_or_file")
        instruction = payload["model_evidence_plan_instruction"]
        self.assertEqual(instruction["schema"], "pointer_gpf.v2.model_evidence_plan_instruction.v1")
        self.assertIn("callMethod", instruction["allowed_actions"])
        self.assertEqual(
            instruction["project_fact_hints"]["candidate_files"][0]["path"],
            "res://scripts/enemies/test_enemy.gd",
        )
        self.assertEqual(instruction["example"]["schema"], "pointer_gpf.v2.model_evidence_plan.v1")

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
        self.assertEqual(payload["artifact_summary"]["by_stage"]["repro_artifact"], "repro.json")
        self.assertEqual(payload["repair_summary"]["repro"]["status"], "bug_reproduced")
        instruction = payload["model_fix_proposal_instruction"]
        self.assertEqual(instruction["schema"], "pointer_gpf.v2.model_fix_proposal_instruction.v1")
        self.assertEqual(instruction["example"]["schema"], "pointer_gpf.v2.model_fix_proposal.v1")

    def test_repair_reported_bug_fix_proposal_instruction_carries_fix_plan_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = repair_reported_bug(
                Path(tmp),
                self._args(),
                collect_bug_report_fn=lambda *_: {"summary": "敌人受击后没有闪红"},
                observe_bug_context_fn=lambda *_: {"status": "observed"},
                plan_bug_repro_flow_fn=lambda *_: {"model_evidence_plan_status": "accepted"},
                run_bug_repro_flow_fn=lambda *_: {
                    "status": "bug_reproduced",
                    "artifact_file": "repro.json",
                    "runtime_evidence_summary": {"record_count": 2},
                },
                plan_bug_fix_fn=lambda *_: {
                    "status": "fix_ready",
                    "candidate_files": [{"path": "res://scripts/enemies/test_enemy.gd"}],
                    "fix_goals": [{"goal": "update shader hit_count after hit"}],
                    "acceptance_checks": [{"evidenceRef": "enemy_hit_count_after"}],
                },
                apply_bug_fix_fn=lambda *_: {},
                rerun_bug_repro_flow_fn=lambda *_: {},
                run_bug_fix_regression_fn=lambda *_: {},
            )

        instruction = payload["model_fix_proposal_instruction"]
        self.assertEqual(
            instruction["candidate_files"][0]["path"],
            "res://scripts/enemies/test_enemy.gd",
        )
        self.assertEqual(instruction["runtime_evidence_summary"]["record_count"], 2)

    def test_repair_reported_bug_reports_fixed_and_verified(self) -> None:
        args = self._args()
        args.fix_proposal_json = '{"candidate_file":"res://scripts/enemy.gd","edits":[]}'
        with tempfile.TemporaryDirectory() as tmp:
            payload = repair_reported_bug(
                Path(tmp),
                args,
                collect_bug_report_fn=lambda *_: {
                    "summary": "敌人受击后没有闪红",
                    "bug_source": "injected",
                    "round_id": "round-1",
                    "bug_id": "bug-1",
                    "injected_bug_kind": "hit_feedback_shader_not_updated",
                },
                observe_bug_context_fn=lambda *_: {"status": "observed"},
                plan_bug_repro_flow_fn=lambda *_: {"model_evidence_plan_status": "accepted"},
                run_bug_repro_flow_fn=lambda *_: {
                    "status": "bug_reproduced",
                    "artifact_file": "repro.json",
                    "runtime_evidence_records": [{"evidence_id": "enemy_hit_count_after"}],
                    "check_summary": {"failed_check_ids": ["check_enemy_hit_count_after_one"]},
                },
                plan_bug_fix_fn=lambda *_: {
                    "status": "fix_ready",
                    "candidate_files": [{"path": "res://scripts/enemy.gd"}],
                    "fix_goals": [{"goal": "sync hit count"}],
                },
                apply_bug_fix_fn=lambda *_: {
                    "status": "fix_applied",
                    "applied_changes": [{"path": "res://scripts/enemy.gd"}],
                    "proposal_artifact": "proposal.json",
                    "application_artifact": "apply.json",
                },
                rerun_bug_repro_flow_fn=lambda *_: {
                    "status": "bug_not_reproduced",
                    "artifact_file": "rerun.json",
                    "runtime_evidence_records": [{"evidence_id": "enemy_hit_count_after"}],
                },
                run_bug_fix_regression_fn=lambda *_: {"status": "passed", "artifact_file": "regression.json"},
            )

        self.assertEqual(payload["status"], "fixed_and_verified")
        self.assertEqual(payload["next_action"], "")
        self.assertIn("repro.json", payload["artifact_files"])
        self.assertEqual(payload["artifact_summary"]["by_stage"]["repro_artifact"], "repro.json")
        self.assertEqual(payload["artifact_summary"]["by_stage"]["proposal_artifact"], "proposal.json")
        self.assertEqual(payload["artifact_summary"]["by_stage"]["application_artifact"], "apply.json")
        self.assertEqual(payload["artifact_summary"]["by_stage"]["rerun_artifact"], "rerun.json")
        self.assertEqual(payload["artifact_summary"]["by_stage"]["regression_artifact"], "regression.json")
        summary = payload["repair_summary"]
        self.assertEqual(summary["schema"], "pointer_gpf.v2.repair_summary.v1")
        self.assertEqual(summary["status"], "fixed_and_verified")
        self.assertEqual(summary["bug_source"], "injected")
        self.assertEqual(summary["repro"]["failed_check_ids"], ["check_enemy_hit_count_after_one"])
        self.assertEqual(summary["repro"]["runtime_evidence_ids"], ["enemy_hit_count_after"])
        self.assertEqual(summary["apply"]["applied_changes"][0]["path"], "res://scripts/enemy.gd")
        self.assertEqual(summary["rerun"]["status"], "bug_not_reproduced")
        self.assertEqual(summary["regression"]["status"], "passed")
        self.assertEqual(payload["user_report"]["schema"], "pointer_gpf.v2.user_repair_report.v1")
        self.assertEqual(payload["user_report"]["sections"]["verification"]["regression_status"], "passed")
        self.assertIn("Repair status: fixed_and_verified", payload["user_report"]["markdown"])


if __name__ == "__main__":
    unittest.main()
