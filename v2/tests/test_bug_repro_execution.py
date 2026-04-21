import argparse
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_repro_execution import run_bug_repro_flow


class BugReproExecutionTests(unittest.TestCase):
    def test_run_bug_repro_flow_marks_bug_not_reproduced_when_flow_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_set": {
                        "assertions": [
                            {"runtime_check": {"hint": "node_exists:GameLevel"}},
                        ]
                    },
                    "candidate_flow": {
                        "steps": [
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ]
                    },
                },
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {"execution": {"status": "passed"}}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

        self.assertEqual(payload["schema"], "pointer_gpf.v2.repro_run.v1")
        self.assertEqual(payload["status"], "bug_not_reproduced")
        self.assertFalse(payload["reproduction_confirmed"])
        self.assertIn("repro_gap", payload)
        self.assertIn("refinement_plan", payload)
        self.assertEqual(payload["repro_gap"]["base_flow_covered_assertions"], [])
        self.assertEqual(payload["refinement_plan"]["status"], "trigger_refinement_needed")
        self.assertEqual(payload["next_action"], "tighten_repro_trigger")

    def test_run_bug_repro_flow_marks_bug_reproduced_when_assertion_step_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_set": {
                        "assertions": [
                            {"runtime_check": {"hint": "node_exists:GameLevel"}},
                        ]
                    },
                    "candidate_flow": {
                        "steps": [
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ]
                    },
                },
                run_basic_flow_tool=lambda *_: (
                    2,
                    {
                        "ok": False,
                        "error": {
                            "code": "TIMEOUT",
                            "message": "bridge did not respond within step_timeout_ms",
                            "details": {"step_id": "wait_gamelevel"},
                        },
                    },
                    False,
                ),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

        self.assertEqual(payload["status"], "bug_reproduced")
        self.assertTrue(payload["reproduction_confirmed"])
        self.assertEqual(payload["refinement_plan"]["status"], "not_needed")

    def test_run_bug_repro_flow_reports_indirect_coverage_gap_for_non_repro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_coverage": [
                        {
                            "assertion_id": "target_scene_reached",
                            "status": "already_covered_by_base_flow",
                        },
                        {
                            "assertion_id": "interaction_should_change_state",
                            "status": "covered_by_related_assertions",
                        },
                    ],
                    "unsupported_assertions": [],
                    "assertion_set": {
                        "assertions": [
                            {"runtime_check": {"hint": "node_exists:GameLevel"}},
                        ]
                    },
                    "candidate_flow": {
                        "steps": [
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ]
                    },
                },
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {"execution": {"status": "passed"}}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

        self.assertEqual(payload["status"], "bug_not_reproduced")
        self.assertIn("interaction_should_change_state", payload["repro_gap"]["indirectly_covered_assertions"])
        self.assertIn("more direct assertion", payload["repro_gap"]["recommended_next_action"])
        self.assertEqual(payload["refinement_plan"]["status"], "refinement_needed")
        self.assertEqual(payload["refinement_plan"]["primary_action"], "add_direct_assertion")
        self.assertTrue(
            any(
                item["type"] == "add_direct_assertion"
                and item["target_assertion"] == "interaction_should_change_state"
                for item in payload["refinement_plan"]["actions"]
            )
        )
        self.assertEqual(payload["next_action"], "add_direct_assertion")

    def test_run_bug_repro_flow_reports_unsupported_assertion_refinement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_coverage": [],
                    "unsupported_assertions": ["interaction_should_change_state"],
                    "assertion_set": {
                        "assertions": [
                            {"runtime_check": {"hint": "node_exists:GameLevel"}},
                        ]
                    },
                    "candidate_flow": {
                        "steps": [
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ]
                    },
                },
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {"execution": {"status": "passed"}}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

        self.assertEqual(payload["status"], "bug_not_reproduced")
        self.assertEqual(payload["refinement_plan"]["status"], "refinement_needed")
        self.assertEqual(payload["refinement_plan"]["primary_action"], "make_assertion_executable")
        self.assertTrue(
            any(
                item["type"] == "make_assertion_executable"
                and item["target_assertion"] == "interaction_should_change_state"
                for item in payload["refinement_plan"]["actions"]
            )
        )
        self.assertEqual(payload["next_action"], "make_assertion_executable")


if __name__ == "__main__":
    unittest.main()
