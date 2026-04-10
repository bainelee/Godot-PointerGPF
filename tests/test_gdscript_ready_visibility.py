"""Tests for gdscript_ready_visibility + integration with scene_interaction_model."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))


class TestMainScenePackedHidden(unittest.TestCase):
    def test_ui_demo_marked_hidden_when_main_menu_hides_ui1(self) -> None:
        from gdscript_ready_visibility import main_scene_packed_hidden_by_scripts

        ex = REPO / "examples/godot_minimal"
        if not (ex / "project.godot").exists():
            self.skipTest("examples/godot_minimal missing")
        hidden = main_scene_packed_hidden_by_scripts(ex, "scenes/main_scene_example.tscn")
        self.assertTrue(hidden.get("scenes/ui/ui_demo_panel_1.tscn"))
        self.assertNotIn("scenes/ui/ui_start_screen.tscn", hidden)


class TestApplyScriptVisibility(unittest.TestCase):
    def test_ready_overrides_tscn_visible(self) -> None:
        from gdscript_ready_visibility import apply_script_visibility_overrides
        from scene_interaction_model import parse_tscn_nodes

        tscn = """
[gd_scene format=3]
[node name="Root" type="Control"]
[node name="Btn" type="Button" parent="."]
offset_right = 50.0
offset_bottom = 50.0
"""
        gd = """
@onready var btn: Button = $Btn
func _ready() -> void:
	btn.visible = false
"""
        nodes = parse_tscn_nodes(tscn)
        st = apply_script_visibility_overrides(nodes, [gd], parse_visible_fn=lambda n: "false" not in n.raw_attrs.get("visible", "true").lower())
        self.assertFalse(st["Btn"])


if __name__ == "__main__":
    unittest.main()
