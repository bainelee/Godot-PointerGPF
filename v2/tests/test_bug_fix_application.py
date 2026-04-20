import argparse
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_fix_application import apply_bug_fix


class BugFixApplicationTests(unittest.TestCase):
    def test_apply_bug_fix_blocks_when_fix_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = apply_bug_fix(
                project_root,
                argparse.Namespace(),
                plan_bug_fix_fn=lambda *_: {
                    "bug_summary": "summary",
                    "status": "fix_not_ready",
                    "next_action": "refine_repro_flow_or_assertions",
                },
            )

        self.assertEqual(payload["schema"], "pointer_gpf.v2.fix_apply.v1")
        self.assertEqual(payload["status"], "fix_not_applied")
        self.assertEqual(payload["next_action"], "refine_repro_flow_or_assertions")

    def test_apply_bug_fix_adds_guarded_button_signal_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "main_menu_flow.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(
                "\n".join(
                    [
                        "extends CanvasLayer",
                        "",
                        "func _ready() -> void:",
                        "\tpass",
                        "",
                        "func _on_start_button_pressed() -> void:",
                        "\tpass",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = apply_bug_fix(
                project_root,
                argparse.Namespace(),
                plan_bug_fix_fn=lambda *_: {
                    "bug_summary": "点击开始游戏没有反应",
                    "status": "fix_ready",
                    "candidate_files": [
                        {
                            "path": "res://scripts/main_menu_flow.gd",
                            "absolute_path": str(script_path),
                        }
                    ],
                    "repro_run": {
                        "repro_flow_plan": {
                            "assertion_set": {
                                "bug_analysis": {
                                    "bug_intake": {
                                        "location_hint": {
                                            "node": "StartButton",
                                        }
                                    },
                                    "suspected_causes": [
                                        {"kind": "button_signal_or_callback_broken"},
                                    ],
                                }
                            }
                        }
                    },
                },
            )

            updated = script_path.read_text(encoding="utf-8")

        self.assertEqual(payload["status"], "fix_applied")
        self.assertIn("_gpf_bind_bug_trigger_signal()", updated)
        self.assertIn('find_child("StartButton"', updated)
        self.assertIn("pressed.connect(_on_start_button_pressed)", updated)

    def test_apply_bug_fix_adds_scene_transition_call_when_handler_exists_but_no_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "main_menu_flow.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(
                "\n".join(
                    [
                        "extends CanvasLayer",
                        "",
                        "func _ready() -> void:",
                        "\tpass",
                        "",
                        "func _on_start_button_pressed() -> void:",
                        "\tprint(\"clicked\")",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = apply_bug_fix(
                project_root,
                argparse.Namespace(),
                plan_bug_fix_fn=lambda *_: {
                    "bug_summary": "点击开始游戏没有反应",
                    "status": "fix_ready",
                    "candidate_files": [
                        {
                            "path": "res://scripts/main_menu_flow.gd",
                            "absolute_path": str(script_path),
                        }
                    ],
                    "repro_run": {
                        "repro_flow_plan": {
                            "assertion_set": {
                                "assertions": [
                                    {
                                        "id": "target_scene_reached",
                                        "target": {"scene": "res://scenes/game_level.tscn"},
                                    }
                                ],
                                "bug_analysis": {
                                    "bug_intake": {
                                        "location_hint": {
                                            "node": "StartButton",
                                        }
                                    },
                                    "suspected_causes": [
                                        {"kind": "scene_transition_not_triggered"},
                                    ],
                                }
                            }
                        }
                    },
                },
            )

            updated = script_path.read_text(encoding="utf-8")

        self.assertEqual(payload["status"], "fix_applied")
        self.assertIn("_gpf_change_to_expected_scene()", updated)
        self.assertIn('change_scene_to_file("res://scenes/game_level.tscn")', updated)
        self.assertIn("strategy", payload["applied_changes"][0])
        self.assertEqual(payload["applied_changes"][0]["strategy"], "add_scene_transition_call")


if __name__ == "__main__":
    unittest.main()
