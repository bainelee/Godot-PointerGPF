from __future__ import annotations

import unittest
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


class GodotMinimalFpsExampleTests(unittest.TestCase):
    def test_fps_scenes_and_scripts_exist(self) -> None:
        root = _repo_root() / "examples" / "godot_minimal"
        must_exist = [
            root / "scenes" / "game_level.tscn",
            root / "scenes" / "player" / "fps_controller.tscn",
            root / "scenes" / "enemies" / "test_enemy.tscn",
            root / "scenes" / "projectiles" / "bullet.tscn",
            root / "scenes" / "ui" / "crosshair.tscn",
            root / "scripts" / "game_level.gd",
            root / "scripts" / "player" / "fps_controller.gd",
            root / "textures" / "triangle_inverted_red.png",
            root / "shaders" / "grid.gdshader",
        ]
        for p in must_exist:
            self.assertTrue(p.is_file(), msg=f"missing {p.relative_to(root)}")

    def test_main_scene_example_lists_ui_instances(self) -> None:
        scene = _repo_root() / "examples" / "godot_minimal" / "scenes" / "main_scene_example.tscn"
        text = scene.read_text(encoding="utf-8")
        self.assertIn("UI1", text)
        self.assertIn("StartScreen", text)
        self.assertIn("ui_dashboard_layout.tscn", text)


if __name__ == "__main__":
    unittest.main()
