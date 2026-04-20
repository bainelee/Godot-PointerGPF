import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_assertions import define_bug_assertions


class BugAssertionsTests(unittest.TestCase):
    def test_define_bug_assertions_returns_assertion_set(self) -> None:
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
                            {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "check_hud", "action": "check", "hint": "node_exists:GamePointerHud"},
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
                            "res://scenes/ui/game_pointer_hud.tscn",
                        ],
                        "project_file_summary": {
                            "total_file_count": 5,
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
            )

            payload = define_bug_assertions(project_root, args)

        self.assertEqual(payload["schema"], "pointer_gpf.v2.assertion_set.v1")
        self.assertEqual(payload["bug_analysis"]["schema"], "pointer_gpf.v2.bug_analysis.v1")
        self.assertTrue(any(item["id"] == "target_scene_reached" for item in payload["assertions"]))
        self.assertTrue(any(item["runtime_check"]["hint"] == "node_exists:GameLevel" for item in payload["assertions"]))


if __name__ == "__main__":
    unittest.main()
