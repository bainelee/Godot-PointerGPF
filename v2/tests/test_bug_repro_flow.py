import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_repro_flow import plan_bug_repro_flow


class BugReproFlowTests(unittest.TestCase):
    def test_plan_bug_repro_flow_reuses_basicflow_and_appends_assertions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '\n'.join(
                    [
                        "[application]",
                        'run/main_scene="res://scenes/main_scene_example.tscn"',
                    ]
                ),
                encoding="utf-8",
            )
            (project_root / "pointer_gpf").mkdir(parents=True, exist_ok=True)
            (project_root / "pointer_gpf" / "basicflow.json").write_text(
                json.dumps(
                    {
                        "flowId": "project_basicflow",
                        "steps": [
                            {"id": "launch_game", "action": "launchGame"},
                            {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                            {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (project_root / "pointer_gpf" / "basicflow.meta.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-14T00:00:00+00:00",
                        "generation_summary": "summary",
                        "related_files": [
                            "project.godot",
                            "res://scenes/main_scene_example.tscn",
                            "res://scripts/main_menu_flow.gd",
                            "res://scenes/game_level.tscn",
                        ],
                        "project_file_summary": {
                            "total_file_count": 4,
                            "script_count": 1,
                            "scene_count": 2,
                        },
                        "last_successful_run_at": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|点击开始游戏",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        self.assertEqual(payload["schema"], "pointer_gpf.v2.repro_flow_plan.v1")
        self.assertEqual(payload["strategy"], "reuse_project_basicflow")
        self.assertTrue(payload["needs_flow_patch"])
        self.assertGreaterEqual(payload["planned_assertion_step_count"], 1)
        self.assertEqual(payload["candidate_flow"]["steps"][-1]["action"], "closeProject")

    def test_plan_bug_repro_flow_marks_state_change_assertion_as_covered_when_target_scene_is_already_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '\n'.join(
                    [
                        "[application]",
                        'run/main_scene="res://scenes/main_scene_example.tscn"',
                    ]
                ),
                encoding="utf-8",
            )
            (project_root / "pointer_gpf").mkdir(parents=True, exist_ok=True)
            (project_root / "pointer_gpf" / "basicflow.json").write_text(
                json.dumps(
                    {
                        "flowId": "project_basicflow",
                        "steps": [
                            {"id": "launch_game", "action": "launchGame"},
                            {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                            {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (project_root / "pointer_gpf" / "basicflow.meta.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-14T00:00:00+00:00",
                        "generation_summary": "summary",
                        "related_files": [
                            "project.godot",
                            "res://scenes/main_scene_example.tscn",
                            "res://scripts/main_menu_flow.gd",
                            "res://scenes/game_level.tscn",
                        ],
                        "project_file_summary": {
                            "total_file_count": 4,
                            "script_count": 1,
                            "scene_count": 2,
                        },
                        "last_successful_run_at": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|点击开始游戏",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        self.assertNotIn("interaction_should_change_state", payload["unsupported_assertions"])
        self.assertEqual(payload["repro_readiness"], "ready_for_repro_run")
        self.assertTrue(
            any(
                item["assertion_id"] == "interaction_should_change_state"
                and item["status"] == "covered_by_related_assertions"
                for item in payload["assertion_coverage"]
            )
        )


if __name__ == "__main__":
    unittest.main()
