"""Tests for static interaction ranking in basic flow design."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))


class TestDesignFlowWeights(unittest.TestCase):
    def test_rank_prefers_medium_over_none(self) -> None:
        import server as srv

        actions = [
            {"id": "a.none", "static_interaction": {"player_click_likelihood": "none"}},
            {"id": "b.med", "static_interaction": {"player_click_likelihood": "medium"}},
        ]
        out = srv._rank_click_actions_by_static_interaction(actions, allow_low_likelihood=False)
        self.assertEqual(out[0]["id"], "b.med")

    def test_enrich_adds_static_interaction_for_scene_button(self) -> None:
        import server as srv

        example = REPO / "examples" / "godot_minimal"
        if not (example / "project.godot").exists():
            self.skipTest("examples/godot_minimal missing")
        fc = {
            "action_candidates": [
                {
                    "id": "x",
                    "kind": "click",
                    "target_hint": "node_name:StartButton",
                    "evidence": ["scene_button:scenes/ui/ui_start_screen.tscn:StartButton"],
                }
            ],
            "assertion_candidates": [],
        }
        from scene_interaction_model import read_viewport_size_from_project

        srv._enrich_flow_candidates_static_interaction(
            example,
            fc,
            read_viewport_size_from_project(example / "project.godot"),
        )
        act = fc["action_candidates"][0]
        self.assertIn("static_interaction", act)
        self.assertEqual(act["static_interaction"].get("player_click_likelihood"), "medium")


if __name__ == "__main__":
    unittest.main()
