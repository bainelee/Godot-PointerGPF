"""Tests for mcp/gameplay_archetype_hints.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MCP = REPO / "mcp"
if str(MCP) not in sys.path:
    sys.path.insert(0, str(MCP))


class TestGameplayArchetypeHints(unittest.TestCase):
    def test_fps_archetype_emits_move_look_shoot_when_signals_match(self) -> None:
        from gameplay_archetype_hints import build_gameplay_understanding

        gu = build_gameplay_understanding(
            inferred_keywords=["ui-heavy"],
            script_method_blob="shoot fire _input is_on_floor",
            scene_root_types=["Node3D", "CharacterBody3D"],
            inputmap_blob="ui_left\nui_right\n",
        )
        self.assertIn("first_person", gu["matched_archetypes"])
        verbs = {v["verb"] for v in gu["project_verbs"]}
        self.assertTrue({"move", "look", "shoot"} & verbs)


if __name__ == "__main__":
    unittest.main()
