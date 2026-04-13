import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.basicflow_generation import (
    BasicFlowGenerationError,
    generate_basicflow_assets,
    generate_basicflow_from_answers,
    generate_basicflow_from_answers_file,
    get_basicflow_generation_questions,
    normalize_generation_answers,
)


class BasicFlowGenerationTests(unittest.TestCase):
    def test_generate_basicflow_assets_writes_required_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="scenes/main.tscn"\n',
                encoding="utf-8",
            )
            (project_root / "scenes").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")

            result = generate_basicflow_assets(
                project_root,
                main_scene_is_entry=True,
                tested_features=["进入主流程", "基础操作"],
                include_screenshot_evidence=True,
            )

            flow_steps = result["flow"]["steps"]
            step_actions = [step["action"] for step in flow_steps]

        self.assertEqual(step_actions[0], "launchGame")
        self.assertIn("wait", step_actions)
        self.assertIn("click", step_actions)
        self.assertIn("check", step_actions)
        self.assertIn("snapshot", step_actions)
        self.assertEqual(step_actions[-1], "closeProject")
        self.assertIn("project.godot", result["meta"]["related_files"])
        self.assertIn("scenes/main.tscn", result["meta"]["related_files"])

    def test_generate_basicflow_assets_prefers_project_specific_path_when_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="res://scenes/main_scene_example.tscn"\n',
                encoding="utf-8",
            )
            (project_root / "scenes").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "ui").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main_scene_example.tscn").write_text(
                '[gd_scene format=3]\n[ext_resource type="PackedScene" path="res://scenes/ui/ui_start_screen.tscn" id="1"]\n[ext_resource type="Script" path="res://scripts/main_menu_flow.gd" id="2"]\n',
                encoding="utf-8",
            )
            (project_root / "scenes" / "ui" / "ui_start_screen.tscn").write_text(
                '[gd_scene format=3]\n[node name="StartButton" type="Button"]\n',
                encoding="utf-8",
            )
            (project_root / "scripts").mkdir(parents=True, exist_ok=True)
            (project_root / "scripts" / "main_menu_flow.gd").write_text(
                'extends Node\nconst GAME_LEVEL := "res://scenes/game_level.tscn"\nfunc _on_start_pressed() -> void:\n\tget_tree().change_scene_to_file(GAME_LEVEL)\n',
                encoding="utf-8",
            )
            (project_root / "scenes" / "game_level.tscn").write_text(
                '[gd_scene format=3]\n[ext_resource type="Script" path="res://scripts/game_level.gd" id="1"]\n[node name="GameLevel" type="Node3D"]\nscript = ExtResource("1")\n',
                encoding="utf-8",
            )
            (project_root / "scripts" / "game_level.gd").write_text(
                'extends Node3D\nconst POINTER_HUD := preload("res://scenes/ui/game_pointer_hud.tscn")\n',
                encoding="utf-8",
            )
            (project_root / "scenes" / "ui" / "game_pointer_hud.tscn").write_text(
                '[gd_scene format=3]\n[node name="GamePointerHud" type="CanvasLayer"]\n',
                encoding="utf-8",
            )

            result = generate_basicflow_assets(
                project_root,
                main_scene_is_entry=True,
                tested_features=["进入主流程", "基础操作"],
                include_screenshot_evidence=False,
            )

        actions = [step["action"] for step in result["flow"]["steps"]]
        self.assertEqual(actions, ["launchGame", "wait", "click", "wait", "check", "closeProject"])
        self.assertEqual(result["flow"]["steps"][1]["until"]["hint"], "node_exists:StartButton")
        self.assertEqual(result["flow"]["steps"][2]["target"]["hint"], "node_name:StartButton")
        self.assertEqual(result["flow"]["steps"][3]["until"]["hint"], "node_exists:GameLevel")
        self.assertEqual(result["flow"]["steps"][4]["hint"], "node_exists:GamePointerHud")
        self.assertIn("Detected target mode: button_to_scene_with_runtime_anchor.", result["meta"]["generation_summary"])
        self.assertIn("res://scripts/main_menu_flow.gd", result["meta"]["related_files"])
        self.assertIn("res://scripts/game_level.gd", result["meta"]["related_files"])
        self.assertIn("res://scenes/ui/game_pointer_hud.tscn", result["meta"]["related_files"])

    def test_generate_basicflow_assets_detects_scene_transition_without_runtime_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="res://scenes/main_scene_example.tscn"\n',
                encoding="utf-8",
            )
            (project_root / "scenes").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "menus").mkdir(parents=True, exist_ok=True)
            (project_root / "scripts").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main_scene_example.tscn").write_text(
                '[gd_scene format=3]\n[ext_resource type="PackedScene" path="res://scenes/menus/title_screen.tscn" id="1"]\n[ext_resource type="Script" path="res://scripts/title_flow.gd" id="2"]\n',
                encoding="utf-8",
            )
            (project_root / "scenes" / "menus" / "title_screen.tscn").write_text(
                '[gd_scene format=3]\n[node name="PlayButton" type="Button"]\n',
                encoding="utf-8",
            )
            (project_root / "scripts" / "title_flow.gd").write_text(
                'extends Node\nfunc _on_play_button_pressed() -> void:\n\tget_tree().change_scene_to_file("res://scenes/combat_room.tscn")\n',
                encoding="utf-8",
            )
            (project_root / "scenes" / "combat_room.tscn").write_text(
                '[gd_scene format=3]\n[node name="CombatRoom" type="Node2D"]\n',
                encoding="utf-8",
            )

            result = generate_basicflow_assets(
                project_root,
                main_scene_is_entry=True,
                tested_features=["进入战斗房间"],
                include_screenshot_evidence=False,
            )

        self.assertEqual(
            [step["action"] for step in result["flow"]["steps"]],
            ["launchGame", "wait", "click", "wait", "check", "closeProject"],
        )
        self.assertEqual(result["flow"]["steps"][1]["until"]["hint"], "node_exists:PlayButton")
        self.assertEqual(result["flow"]["steps"][2]["target"]["hint"], "node_name:PlayButton")
        self.assertEqual(result["flow"]["steps"][3]["until"]["hint"], "node_exists:CombatRoom")
        self.assertEqual(result["flow"]["steps"][4]["hint"], "node_exists:CombatRoom")
        self.assertIn("Detected target mode: button_to_scene_root.", result["meta"]["generation_summary"])
        self.assertIn("res://scripts/title_flow.gd", result["meta"]["related_files"])
        self.assertIn("res://scenes/combat_room.tscn", result["meta"]["related_files"])

    def test_generate_basicflow_assets_requires_entry_scene_when_main_scene_is_not_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text("[application]\n", encoding="utf-8")

            with self.assertRaises(BasicFlowGenerationError):
                generate_basicflow_assets(
                    project_root,
                    main_scene_is_entry=False,
                    tested_features=["基础操作"],
                    include_screenshot_evidence=False,
                )

    def test_generate_basicflow_from_answers_file_accepts_string_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="scenes/main.tscn"\n',
                encoding="utf-8",
            )
            (project_root / "scenes").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")
            answer_file = project_root / "answers.json"
            answer_file.write_text(
                json.dumps(
                    {
                        "main_scene_is_entry": True,
                        "tested_features": "进入主流程, 基础操作",
                        "include_screenshot_evidence": False,
                    }
                ),
                encoding="utf-8",
            )

            result = generate_basicflow_from_answers_file(project_root, answer_file)

        self.assertEqual(result["flow"]["flowId"], "project_basicflow")
        self.assertFalse(any(step["action"] == "snapshot" for step in result["flow"]["steps"]))

    def test_generate_basicflow_from_answers_accepts_inline_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="scenes/main.tscn"\n',
                encoding="utf-8",
            )
            (project_root / "scenes").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")

            result = generate_basicflow_from_answers(
                project_root,
                {
                    "main_scene_is_entry": True,
                    "tested_features": "进入主流程, 基础操作",
                    "include_screenshot_evidence": False,
                },
            )

        self.assertEqual(result["flow"]["flowId"], "project_basicflow")
        self.assertEqual(result["flow"]["steps"][-1]["action"], "closeProject")

    def test_normalize_generation_answers_rejects_invalid_features_type(self) -> None:
        with self.assertRaises(BasicFlowGenerationError):
            normalize_generation_answers(
                {
                    "main_scene_is_entry": True,
                    "tested_features": 123,
                    "include_screenshot_evidence": False,
                }
            )

    def test_get_basicflow_generation_questions_includes_project_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="res://scenes/main.tscn"\n',
                encoding="utf-8",
            )

            result = get_basicflow_generation_questions(project_root)

        self.assertEqual(result["status"], "questions_ready")
        self.assertEqual(result["question_count"], 3)
        self.assertEqual(result["questions"][0]["project_hint"], "res://scenes/main.tscn")


if __name__ == "__main__":
    unittest.main()
