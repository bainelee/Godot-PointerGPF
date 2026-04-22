import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_report import collect_bug_report


class BugReportTests(unittest.TestCase):
    def test_collect_bug_report_normalizes_minimal_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应。还停留在主菜单。",
                bug_summary=None,
                expected_behavior="点击后应该进入游戏关卡",
                steps_to_trigger="启动游戏|等待主菜单|点击开始游戏",
                location_scene="res://scenes/boot.tscn",
                location_node="StartButton",
                location_script="",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = collect_bug_report(project_root, args)

        self.assertEqual(payload["schema"], "pointer_gpf.v2.bug_intake.v1")
        self.assertEqual(payload["summary"], "点击开始游戏没有反应")
        self.assertEqual(payload["steps_to_trigger"], ["启动游戏", "等待主菜单", "点击开始游戏"])
        self.assertEqual(payload["location_hint"]["node"], "StartButton")
        self.assertEqual(payload["extra_context"]["user_words"], "点击开始游戏没有反应。还停留在主菜单。")

    def test_collect_bug_report_requires_expected_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="",
                steps_to_trigger="",
                location_scene="",
                location_node="",
                location_script="",
                frequency_hint="",
                severity_hint="",
            )

            with self.assertRaisesRegex(ValueError, "collect_bug_report requires"):
                collect_bug_report(project_root, args)

    def test_collect_bug_report_loads_payload_from_bug_case_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            bug_case_file = project_root / "pointer_gpf" / "tmp" / "bug_dev_rounds" / "r1" / "bug_cases" / "b1.json"
            bug_case_file.parent.mkdir(parents=True, exist_ok=True)
            bug_case_file.write_text(
                json.dumps(
                    {
                        "schema": "pointer_gpf.v2.test_project_bug_case.v1",
                        "round_id": "r1",
                        "bug_id": "b1",
                        "bug_source": "injected",
                        "injected_bug_kind": "scene_transition_not_triggered",
                        "bug_case_file": str(bug_case_file),
                        "bug_report_payload": {
                            "bug_report": "点击开始后停留在开始界面",
                            "bug_summary": "开始按钮不切场景",
                            "expected_behavior": "应该进入关卡",
                            "steps_to_trigger": ["启动游戏", "点击开始游戏"],
                            "location_scene": "res://scenes/main_scene_example.tscn",
                            "location_node": "StartButton",
                            "location_script": "res://scripts/main_menu_flow.gd",
                            "frequency_hint": "always",
                            "severity_hint": "core_progression_blocker",
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                bug_case_file=str(bug_case_file),
                bug_report=None,
                bug_summary=None,
                expected_behavior=None,
                steps_to_trigger=None,
                location_scene=None,
                location_node=None,
                location_script=None,
                frequency_hint=None,
                severity_hint=None,
                round_id=None,
                bug_id=None,
                bug_kind=None,
            )

            payload = collect_bug_report(project_root, args)

            self.assertEqual(payload["summary"], "开始按钮不切场景")
            self.assertEqual(payload["round_id"], "r1")
            self.assertEqual(payload["bug_id"], "b1")
            self.assertEqual(payload["bug_source"], "injected")
            self.assertEqual(payload["steps_to_trigger"], ["启动游戏", "点击开始游戏"])


if __name__ == "__main__":
    unittest.main()
