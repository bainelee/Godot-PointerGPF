import argparse
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_fix_planning import plan_bug_fix


class BugFixPlanningTests(unittest.TestCase):
    def test_plan_bug_fix_returns_fix_not_ready_when_bug_not_reproduced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = plan_bug_fix(
                project_root,
                argparse.Namespace(),
                run_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "status": "bug_not_reproduced",
                },
            )

        self.assertEqual(payload["schema"], "pointer_gpf.v2.fix_plan.v1")
        self.assertEqual(payload["status"], "fix_not_ready")
        self.assertEqual(payload["next_action"], "refine_repro_flow_or_assertions")

    def test_plan_bug_fix_returns_candidates_when_bug_reproduced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = plan_bug_fix(
                project_root,
                argparse.Namespace(),
                run_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "点击开始游戏没有反应",
                    "status": "bug_reproduced",
                    "repro_flow_plan": {
                        "assertion_set": {
                            "bug_analysis": {
                                "bug_intake": {
                                    "location_hint": {
                                        "script": "res://scripts/main_menu_flow.gd",
                                    }
                                },
                                "suspected_causes": [
                                    {"kind": "button_signal_or_callback_broken"},
                                    {"kind": "scene_transition_not_triggered"},
                                ],
                                "affected_artifacts": {
                                    "scripts": ["res://scripts/main_menu_flow.gd", "res://scripts/game_level.gd"],
                                    "scenes": ["res://scenes/main_scene_example.tscn"],
                                },
                            }
                        }
                    },
                },
            )

        self.assertEqual(payload["status"], "fix_ready")
        self.assertTrue(any(item["path"] == "res://scripts/main_menu_flow.gd" for item in payload["candidate_files"]))
        self.assertTrue(any("signal path" in item for item in payload["fix_goals"]))


if __name__ == "__main__":
    unittest.main()
