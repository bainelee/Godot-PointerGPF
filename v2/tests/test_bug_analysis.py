import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_analysis import analyze_bug_report


class BugAnalysisTests(unittest.TestCase):
    def test_analyze_bug_report_builds_project_scoped_payload(self) -> None:
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
                            {"id": "launch", "action": "launchGame"},
                            {"id": "click_start", "action": "click", "target": {"hint": "node_name:StartButton"}},
                            {"id": "close", "action": "closeProject"},
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

            payload = analyze_bug_report(project_root, args)

        self.assertEqual(payload["schema"], "pointer_gpf.v2.bug_analysis.v1")
        self.assertEqual(payload["bug_intake"]["schema"], "pointer_gpf.v2.bug_intake.v1")
        self.assertIn("res://scenes/main_scene_example.tscn", payload["affected_artifacts"]["scenes"])
        self.assertIn("res://scripts/main_menu_flow.gd", payload["affected_artifacts"]["scripts"])
        self.assertTrue(any(item["kind"] == "button_signal_or_callback_broken" for item in payload["suspected_causes"]))
        self.assertTrue(any("project startup scene is" in item for item in payload["evidence"]))


if __name__ == "__main__":
    unittest.main()
