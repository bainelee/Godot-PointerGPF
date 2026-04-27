import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_observation import observe_bug_context


class BugObservationTests(unittest.TestCase):
    def test_observe_bug_context_returns_project_runtime_summary(self) -> None:
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
            tmp_dir = project_root / "pointer_gpf" / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            (project_root / "pointer_gpf" / "basicflow.json").write_text(
                json.dumps(
                    {
                        "flowId": "project_basicflow",
                        "steps": [
                            {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                            {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                            {"id": "check_gamelevel", "action": "check", "hint": "node_exists:GameLevel"},
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
                        ],
                        "project_file_summary": {
                            "total_file_count": 3,
                            "script_count": 1,
                            "scene_count": 2,
                        },
                        "last_successful_run_at": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (project_root / "scenes" / "main_scene_example.tscn").parent.mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main_scene_example.tscn").write_text(
                '\n'.join(
                    [
                        '[gd_scene format=3]',
                        '[ext_resource type="Script" path="res://scripts/main_menu_flow.gd" id="1_menu"]',
                        '[node name="MainSceneExample" type="Node"]',
                        'script = ExtResource("1_menu")',
                    ]
                ),
                encoding="utf-8",
            )
            (project_root / "scenes" / "game_level.tscn").write_text(
                '\n'.join(
                    [
                        '[gd_scene format=3]',
                        '[ext_resource type="Script" path="res://scripts/game_level.gd" id="1_level"]',
                        '[ext_resource type="PackedScene" path="res://scenes/enemies/test_enemy.tscn" id="2_enemy"]',
                        '[node name="GameLevel" type="Node3D"]',
                        'script = ExtResource("1_level")',
                        '[node name="TestEnemy" parent="." instance=ExtResource("2_enemy")]',
                    ]
                ),
                encoding="utf-8",
            )
            (project_root / "scenes" / "enemies").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "enemies" / "test_enemy.tscn").write_text(
                '\n'.join(
                    [
                        '[gd_scene format=3]',
                        '[ext_resource type="Script" path="res://scripts/enemies/test_enemy.gd" id="1_enemy"]',
                        '[node name="TestEnemy" type="Node3D" groups=["enemy"]]',
                        'script = ExtResource("1_enemy")',
                        '[node name="Sprite3D" type="Sprite3D" parent="."]',
                        '[connection signal="hit_received" from="." to="." method="_apply_hit_effect"]',
                    ]
                ),
                encoding="utf-8",
            )
            (project_root / "scripts" / "enemies").mkdir(parents=True, exist_ok=True)
            (project_root / "scripts" / "main_menu_flow.gd").parent.mkdir(parents=True, exist_ok=True)
            (project_root / "scripts" / "main_menu_flow.gd").write_text(
                "extends Node\nfunc _on_start_button_pressed() -> void:\n\tpass\n",
                encoding="utf-8",
            )
            (project_root / "scripts" / "game_level.gd").write_text(
                'extends Node3D\nconst ENEMY := preload("res://scenes/enemies/test_enemy.tscn")\n',
                encoding="utf-8",
            )
            (project_root / "scripts" / "enemies" / "test_enemy.gd").write_text(
                '\n'.join(
                    [
                        "extends Node3D",
                        "var _hit_material: ShaderMaterial",
                        "func _on_bullet_hit(hit_position: Vector3) -> bool:",
                        "\treturn _apply_hit_effect(hit_position)",
                        "func _apply_hit_effect(hit_position: Vector3) -> bool:",
                        '\t_hit_material.set_shader_parameter("hit_count", 1)',
                        "\treturn true",
                    ]
                ),
                encoding="utf-8",
            )
            (tmp_dir / "runtime_diagnostics.json").write_text(
                json.dumps(
                    {
                        "severity": "error",
                        "items": [
                            {"kind": "engine_log_error", "message": "scene change failed"},
                            {"kind": "bridge_error", "message": "runtime stalled"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (tmp_dir / "last_bug_repro_result.json").write_text(
                json.dumps(
                    {
                        "status": "bug_reproduced",
                        "failed_phase": "postcondition",
                        "next_action": "inspect_failure_before_fixing",
                        "check_summary": {
                            "failed_check_ids": ["postcondition_check_0_target_scene_reached"],
                        },
                        "runtime_evidence_summary": {
                            "record_count": 1,
                            "failed_evidence_ids": ["enemy_modulate_window"],
                        },
                        "artifact_file": str(tmp_dir / "last_bug_repro_result.json"),
                        "blocking_point": "",
                        "raw_run_result": {
                            "error": {
                                "details": {
                                    "step_id": "wait_gamelevel",
                                }
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (tmp_dir / "last_bug_fix_verification_summary.json").write_text(
                json.dumps(
                    {
                        "status": "fix_verified",
                        "reason": "rerun and regression passed",
                        "round_id": "round-001",
                        "bug_id": "bug-001",
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

            payload = observe_bug_context(project_root, args)

        self.assertEqual(payload["schema"], "pointer_gpf.v2.bug_observation.v1")
        self.assertEqual(payload["startup_scene"], "res://scenes/main_scene_example.tscn")
        self.assertTrue(payload["basicflow_summary"]["exists"])
        self.assertEqual(payload["runtime_diagnostics"]["blocking_count"], 2)
        self.assertEqual(payload["latest_repro_result"]["status"], "bug_reproduced")
        self.assertEqual(payload["latest_repro_result"]["check_summary"]["failed_check_ids"], ["postcondition_check_0_target_scene_reached"])
        self.assertEqual(payload["latest_runtime_evidence_summary"]["record_count"], 1)
        self.assertIn("sample", payload["runtime_evidence_capabilities"]["actions"])
        self.assertEqual(payload["latest_fix_verification"]["status"], "fix_verified")
        self.assertIn("res://scripts/main_menu_flow.gd", payload["candidate_file_read_order"])
        static_observation = payload["project_static_observation"]
        self.assertEqual(static_observation["schema"], "pointer_gpf.v2.project_static_observation.v1")
        self.assertTrue(
            any(item["path"] == "res://scripts/enemies/test_enemy.gd" for item in static_observation["candidate_files"])
        )
        self.assertTrue(
            any(item["method"] == "_apply_hit_effect" for item in static_observation["candidate_scripts"])
        )
        self.assertTrue(any(item["node"] == "Sprite3D" for item in static_observation["candidate_nodes"]))
        self.assertTrue(any(item["method"] == "_apply_hit_effect" for item in static_observation["signal_connections"]))
        self.assertTrue(any(item["term"] == "hit_count" for item in static_observation["visual_state_surfaces"]))
        self.assertTrue(
            any(
                item.get("metric", {}).get("kind") == "shader_param"
                for item in static_observation["runtime_evidence_target_candidates"]
            )
        )


if __name__ == "__main__":
    unittest.main()
