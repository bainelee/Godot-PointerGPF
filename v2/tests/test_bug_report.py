import argparse
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


if __name__ == "__main__":
    unittest.main()
