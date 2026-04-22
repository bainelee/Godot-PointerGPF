import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_investigation import plan_bug_investigation


class BugInvestigationPlanTests(unittest.TestCase):
    def test_plan_bug_investigation_returns_runtime_actions_checks_and_branches(self) -> None:
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
                            {"id": "check_gamepointerhud", "action": "check", "hint": "node_exists:GamePointerHud"},
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
                        "generated_at": "2026-04-22T00:00:00+00:00",
                        "generation_summary": "summary",
                        "related_files": [
                            "res://scenes/main_scene_example.tscn",
                            "res://scripts/main_menu_flow.gd",
                            "res://scenes/game_level.tscn",
                            "res://scenes/ui/game_pointer_hud.tscn",
                        ],
                        "project_file_summary": {
                            "total_file_count": 4,
                            "script_count": 1,
                            "scene_count": 3,
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
                bug_case_file="",
            )

            payload = plan_bug_investigation(project_root, args)

        self.assertEqual(payload["schema"], "pointer_gpf.v2.bug_investigation_plan.v1")
        self.assertEqual(payload["recommended_next_action"], "run_bug_repro_flow")
        self.assertTrue(any(item["action"] == "click" for item in payload["runtime_action_groups"]["trigger"]))
        self.assertEqual(payload["executable_check_set"]["schema"], "pointer_gpf.v2.check_set.v1")
        self.assertTrue(any(item["mapped_step_id"] == "wait_gamelevel" for item in payload["executable_check_set"]["checks"]))
        self.assertTrue(any(item["assertion_id"] == "target_scene_reached" for item in payload["check_candidates"]))
        self.assertTrue(any(item["when"] == "trigger_failed" for item in payload["failure_branches"]))
        self.assertTrue(payload["repair_focus"])


if __name__ == "__main__":
    unittest.main()
