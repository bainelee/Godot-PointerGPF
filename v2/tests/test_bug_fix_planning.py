import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_fix_planning import plan_bug_fix


class BugFixPlanningTests(unittest.TestCase):
    def test_plan_bug_fix_returns_fix_not_ready_when_no_repro_artifact_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = plan_bug_fix(project_root, argparse.Namespace(bug_report="点击开始游戏没有反应", bug_summary=None))

        self.assertEqual(payload["schema"], "pointer_gpf.v2.fix_plan.v1")
        self.assertEqual(payload["status"], "fix_not_ready")
        self.assertEqual(payload["next_action"], "run_bug_repro_flow_first")

    def test_plan_bug_fix_returns_fix_not_ready_when_artifact_is_not_bug_reproduced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = plan_bug_fix(
                project_root,
                argparse.Namespace(bug_report="点击开始游戏没有反应", bug_summary=None),
                load_repro_result_fn=lambda _: {
                    "bug_summary": "点击开始游戏没有反应",
                    "status": "precondition_failed",
                    "next_action": "inspect_precondition_failure",
                },
            )

        self.assertEqual(payload["status"], "fix_not_ready")
        self.assertEqual(payload["next_action"], "inspect_precondition_failure")

    def test_plan_bug_fix_returns_fix_not_ready_when_artifact_belongs_to_another_bug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = plan_bug_fix(
                project_root,
                argparse.Namespace(bug_report="点击开始游戏没有反应", bug_summary=None, location_node="StartButton"),
                load_repro_result_fn=lambda _: {
                    "bug_summary": "暂停菜单打不开",
                    "bug_identity": {"node": "PauseButton"},
                    "status": "bug_reproduced",
                },
            )

        self.assertEqual(payload["status"], "fix_not_ready")
        self.assertEqual(payload["next_action"], "rerun_bug_repro_flow_for_this_bug")

    def test_plan_bug_fix_returns_candidates_when_persisted_artifact_confirms_repro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = plan_bug_fix(
                project_root,
                argparse.Namespace(
                    bug_report="点击开始游戏没有反应",
                    bug_summary=None,
                    location_node="StartButton",
                    location_scene="res://scenes/main_scene_example.tscn",
                ),
                load_repro_result_fn=lambda _: {
                    "bug_summary": "点击开始游戏没有反应",
                    "bug_identity": {"node": "StartButton", "scene": "res://scenes/main_scene_example.tscn"},
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
