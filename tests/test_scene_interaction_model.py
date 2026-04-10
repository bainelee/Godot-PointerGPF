"""Tests for mcp/scene_interaction_model.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MCP = REPO / "mcp"
if str(MCP) not in sys.path:
    sys.path.insert(0, str(MCP))

MINIMAL_HIDDEN = """
[gd_scene format=3]
[node name="Root" type="Control"]
visible = false
[node name="Btn" type="Button" parent="."]
offset_right = 100.0
offset_bottom = 40.0
"""


class TestParseTscnNodes(unittest.TestCase):
    def test_parse_ui_start_screen_has_start_button_under_start_screen(self) -> None:
        from scene_interaction_model import parse_tscn_nodes

        root = REPO / "examples/godot_minimal"
        text = (root / "scenes/ui/ui_start_screen.tscn").read_text(encoding="utf-8")
        nodes = parse_tscn_nodes(text)
        by_name = {n.name: n for n in nodes}
        self.assertIn("StartScreen", by_name)
        self.assertIn("StartButton", by_name)
        self.assertEqual(by_name["StartButton"].parent_path, ".")


class TestViewportAndRect(unittest.TestCase):
    def test_start_button_approx_rect_inside_viewport(self) -> None:
        from scene_interaction_model import control_screen_rect, parse_tscn_nodes, read_viewport_size_from_project

        root = REPO / "examples/godot_minimal"
        text = (root / "scenes/ui/ui_start_screen.tscn").read_text(encoding="utf-8")
        nodes = parse_tscn_nodes(text)
        vw, vh = read_viewport_size_from_project(root / "project.godot")
        rect = control_screen_rect(nodes, "StartButton", viewport=(vw, vh))
        self.assertIsNotNone(rect)
        assert rect is not None
        x, y, w, h = rect
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, vw + 1)
        self.assertLessEqual(y + h, vh + 1)


class TestHiddenAncestor(unittest.TestCase):
    def test_button_under_invisible_ancestor_flagged(self) -> None:
        from scene_interaction_model import parse_tscn_nodes, summarize_control_interaction

        nodes = parse_tscn_nodes(MINIMAL_HIDDEN)
        s = summarize_control_interaction(nodes, "Btn", viewport=(1920, 1080))
        self.assertFalse(s["ancestor_visible"])
        self.assertIn(s["player_click_likelihood"], ("low", "none"))


if __name__ == "__main__":
    unittest.main()
