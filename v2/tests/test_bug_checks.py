import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_checks import define_bug_checks, summarize_check_results


class BugChecksTests(unittest.TestCase):
    def test_define_bug_checks_returns_mapped_runtime_checks(self) -> None:
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
                            {"id": "check_startbutton_hidden", "action": "check", "hint": "node_hidden:StartButton"},
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (project_root / "pointer_gpf" / "basicflow.meta.json").write_text(
                json.dumps({"related_files": ["res://scripts/main_menu_flow.gd"]}, ensure_ascii=False),
                encoding="utf-8",
            )

            args = argparse.Namespace(
                bug_report="点击开始游戏后没有进入关卡",
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

            payload = define_bug_checks(project_root, args)

        self.assertEqual(payload["schema"], "pointer_gpf.v2.check_set.v1")
        self.assertTrue(any(item["source_assertion_id"] == "interaction_target_present" for item in payload["checks"]))
        self.assertTrue(all(str(item["mapped_step_id"]).strip() for item in payload["checks"]))

    def test_summarize_check_results_marks_failed_and_not_run_checks(self) -> None:
        candidate_flow = {
            "steps": [
                {"id": "launch_game", "action": "launchGame"},
                {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                {"id": "check_pointerhud", "action": "check", "hint": "node_exists:GamePointerHud"},
            ]
        }
        checks = [
            {
                "check_id": "precondition_check_0",
                "source_assertion_id": "interaction_target_present",
                "stage": "precondition",
                "kind": "runtime_hint",
                "action": "wait",
                "hint": "node_exists:StartButton",
                "mapped_step_id": "wait_startbutton",
            },
            {
                "check_id": "postcondition_check_0",
                "source_assertion_id": "target_scene_reached",
                "stage": "postcondition",
                "kind": "scene_active",
                "action": "wait",
                "hint": "node_exists:GameLevel",
                "mapped_step_id": "wait_gamelevel",
            },
            {
                "check_id": "postcondition_check_1",
                "source_assertion_id": "hud_present",
                "stage": "postcondition",
                "kind": "runtime_hint",
                "action": "check",
                "hint": "node_exists:GamePointerHud",
                "mapped_step_id": "check_pointerhud",
            },
        ]

        payload = summarize_check_results(
            candidate_flow,
            checks,
            run_ok=False,
            failed_step_id="wait_gamelevel",
            failure_status="bug_reproduced",
            error_code="TIMEOUT",
            error_message="target scene never appeared",
        )

        self.assertEqual(payload["summary"]["failed_check_ids"], ["postcondition_check_0"])
        self.assertEqual(payload["results"][0]["status"], "passed")
        self.assertEqual(payload["results"][1]["status"], "failed")
        self.assertEqual(payload["results"][2]["status"], "not_run")


if __name__ == "__main__":
    unittest.main()
