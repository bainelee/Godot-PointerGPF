import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.test_project_bug_case import load_bug_case
from v2.mcp_core.test_project_bug_seed import seed_test_project_bug


class TestProjectBugSeedTests(unittest.TestCase):
    def test_seed_test_project_bug_injects_button_callback_bug_and_writes_bug_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "main_menu_flow.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(
                "extends Node\n\nfunc _on_start_button_pressed() -> void:\n\tprint(\"ok\")\n",
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "round_id": "round-003",
                    "bug_id": "bug-003",
                    "bug_kind": "button_signal_or_callback_broken",
                    "bug_report": "点击开始没有反应",
                    "bug_summary": "开始按钮无反应",
                    "expected_behavior": "应该进入关卡",
                    "steps_to_trigger": "启动游戏|点击开始",
                    "location_scene": "res://scenes/main_scene_example.tscn",
                    "location_node": "StartButton",
                    "location_script": "res://scripts/main_menu_flow.gd",
                    "frequency_hint": "always",
                    "severity_hint": "core_progression_blocker",
                    "files_to_record": "",
                    "handler_name": "",
                },
            )()

            payload = seed_test_project_bug(project_root, args)

            self.assertEqual(payload["status"], "bug_seeded")
            script_text = script_path.read_text(encoding="utf-8")
            self.assertIn("gpf_seeded_bug:button_callback_disabled", script_text)
            bug_case = load_bug_case(payload["bug_case_file"])
            self.assertEqual(bug_case["round_id"], "round-003")
            self.assertEqual(bug_case["injected_bug_kind"], "button_signal_or_callback_broken")
            self.assertEqual(bug_case["affected_files"][0]["project_relative_path"], "scripts/main_menu_flow.gd")

    def test_seed_test_project_bug_disables_scene_transition_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "main_menu_flow.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(
                "extends Node\n\nfunc _on_start_button_pressed() -> void:\n\tvar err := tree.change_scene_to_file(GAME_LEVEL)\n",
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "round_id": "round-004",
                    "bug_id": "bug-004",
                    "bug_kind": "scene_transition_not_triggered",
                    "bug_report": "点击开始后仍停留在开始界面",
                    "bug_summary": "场景没有切换",
                    "expected_behavior": "应该进入关卡",
                    "steps_to_trigger": "启动游戏|点击开始",
                    "location_scene": "res://scenes/main_scene_example.tscn",
                    "location_node": "StartButton",
                    "location_script": "res://scripts/main_menu_flow.gd",
                    "frequency_hint": "always",
                    "severity_hint": "core_progression_blocker",
                    "files_to_record": "",
                    "handler_name": "",
                },
            )()

            payload = seed_test_project_bug(project_root, args)

            self.assertEqual(payload["status"], "bug_seeded")
            script_text = script_path.read_text(encoding="utf-8")
            self.assertIn("gpf_seeded_bug:scene_transition_disabled", script_text)
            self.assertNotIn("change_scene_to_file", script_text)

    def test_seed_test_project_bug_renames_button_node_in_scene_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            scene_path = project_root / "scenes" / "ui" / "ui_start_screen.tscn"
            scene_path.parent.mkdir(parents=True, exist_ok=True)
            scene_path.write_text(
                "\n".join(
                    [
                        '[gd_scene format=3]',
                        "",
                        '[node name="StartScreen" type="ColorRect"]',
                        'color = Color(1, 1, 1, 1)',
                        "",
                        '[node name="StartButton" type="Button" parent="."]',
                        'text = "Start Game"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "round_id": "round-005",
                    "bug_id": "bug-005",
                    "bug_kind": "button_node_renamed_in_scene",
                    "bug_report": "开始按钮节点不存在，无法进入游戏",
                    "bug_summary": "开始按钮节点被重命名",
                    "expected_behavior": "开始按钮节点应该存在并可以点击",
                    "steps_to_trigger": "启动游戏|点击开始",
                    "location_scene": "res://scenes/ui/ui_start_screen.tscn",
                    "location_node": "StartButton",
                    "location_script": "",
                    "frequency_hint": "always",
                    "severity_hint": "core_progression_blocker",
                    "files_to_record": "",
                    "handler_name": "",
                },
            )()

            payload = seed_test_project_bug(project_root, args)

            self.assertEqual(payload["status"], "bug_seeded")
            scene_text = scene_path.read_text(encoding="utf-8")
            self.assertIn('[node name="StartButtonSeededBug" type="Button" parent="."]', scene_text)
            bug_case = load_bug_case(payload["bug_case_file"])
            self.assertEqual(bug_case["affected_files"][0]["project_relative_path"], "scenes/ui/ui_start_screen.tscn")
            self.assertEqual(bug_case["expected_verification_target"]["expected_repro_status"], "trigger_failed")

    def test_seed_test_project_bug_disables_pointer_hud_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "game_level.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(
                "extends Node3D\n\nfunc _ready() -> void:\n\tadd_child(POINTER_HUD.instantiate())\n",
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "round_id": "round-006",
                    "bug_id": "bug-006",
                    "bug_kind": "pointer_hud_not_spawned",
                    "bug_report": "进入关卡后没有看到指针模式 HUD",
                    "bug_summary": "关卡 HUD 没有出现",
                    "expected_behavior": "进入关卡后应该出现 HUD",
                    "steps_to_trigger": "启动游戏|点击开始|等待关卡加载",
                    "location_scene": "res://scenes/game_level.tscn",
                    "location_node": "GamePointerHud",
                    "location_script": "res://scripts/game_level.gd",
                    "frequency_hint": "always",
                    "severity_hint": "major",
                    "files_to_record": "",
                    "handler_name": "",
                },
            )()

            payload = seed_test_project_bug(project_root, args)

            self.assertEqual(payload["status"], "bug_seeded")
            script_text = script_path.read_text(encoding="utf-8")
            self.assertIn("gpf_seeded_bug:pointer_hud_not_spawned", script_text)
            bug_case = load_bug_case(payload["bug_case_file"])
            self.assertEqual(bug_case["injected_bug_kind"], "pointer_hud_not_spawned")
            self.assertEqual(bug_case["affected_files"][0]["project_relative_path"], "scripts/game_level.gd")


if __name__ == "__main__":
    unittest.main()
