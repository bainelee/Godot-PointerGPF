"""Tests for operational profile (phased runtime analysis)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_MCP = _REPO / "mcp"
if str(_MCP) not in sys.path:
    sys.path.insert(0, str(_MCP))


class TestOperationalProfileGodotMinimal(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _REPO
        self.example = self.repo / "examples" / "godot_minimal"

    def test_ext_id_map_avoids_uid_false_positive(self) -> None:
        from operational_profile import _all_gd_scripts_in_tscn, _ext_id_map

        tscn = (self.example / "scenes" / "main_scene_example.tscn").read_text(encoding="utf-8")
        id_map = _ext_id_map(tscn)
        self.assertIn("6_flow", id_map)
        self.assertEqual(id_map["6_flow"], "scripts/main_menu_flow.gd")
        self.assertNotIn("uid://hs15ae123hau", id_map)
        scripts = _all_gd_scripts_in_tscn(self.example, "scenes/main_scene_example.tscn")
        self.assertEqual(scripts, ["scripts/main_menu_flow.gd"])

    def test_change_scene_targets_main_menu(self) -> None:
        from operational_profile import _change_scene_targets

        gd = (self.example / "scripts" / "main_menu_flow.gd").read_text(encoding="utf-8")
        targets = _change_scene_targets(gd)
        self.assertIn("scenes/game_level.tscn", targets)

    def test_bundle_has_transitions_and_phases(self) -> None:
        import server as mcp_server
        from operational_profile import build_operational_profile_bundle

        if not (self.example / "project.godot").exists():
            self.skipTest("examples/godot_minimal missing")
        scan = [
            "scripts",
            "scenes",
            "addons",
            "datas",
            "docs",
            "flows",
            "tests",
            "test",
            "src",
        ]
        files = mcp_server._scan_files(self.example, scan, 2500)
        bundle = build_operational_profile_bundle(
            self.example,
            script_signals=mcp_server._extract_script_signals(self.example, files),
            scene_signals=mcp_server._extract_scene_signals(self.example, files),
            inferred_keywords=mcp_server._infer_keywords(files),
        )
        phases = bundle.data.get("runtime_phases")
        self.assertIsInstance(phases, list)
        self.assertGreaterEqual(len(phases), 2)
        trans = phases[1].get("scene_transitions") or []
        self.assertTrue(any(t.get("target_scene", "").endswith("game_level.tscn") for t in trans))
        mu = (bundle.data.get("mcp_usage") or {}) if isinstance(bundle.data.get("mcp_usage"), dict) else {}
        self.assertIn("basic_flow_game_type_reference", mu)
        self.assertEqual(mu.get("basic_flow_usage_and_nl_reference"), "docs/mcp-basic-test-flow-reference-usage.md")
        self.assertTrue(any("mcp-basic-test-flow-game-type-expectations" in str(r) for r in (mu.get("rules") or [])))

        self.assertIn("ui_interaction_model", bundle.data)
        uim = bundle.data["ui_interaction_model"]
        pk = uim.get("packed_scenes_hidden_by_main_ready") or {}
        self.assertTrue(pk.get("scenes/ui/ui_demo_panel_1.tscn"))
        demo_btns = (uim.get("by_scene") or {}).get("scenes/ui/ui_demo_panel_1.tscn", {}).get("buttons") or {}
        self.assertTrue(demo_btns)
        self.assertEqual(
            next(iter(demo_btns.values())).get("runtime_visibility_source"),
            "parent_scene_ready",
        )
        self.assertIn("gameplay_understanding", bundle.data)

    def test_design_flow_uses_start_then_level_ui(self) -> None:
        import server as srv

        if not (self.example / "project.godot").exists():
            self.skipTest("examples/godot_minimal missing")
        ctx = srv.ServerCtx(
            repo_root=self.repo,
            template_plugin_dir=self.repo / "godot_plugin_template" / "addons" / "pointer_gpf",
        )
        cfg = srv._resolve_runtime_config(ctx, {"project_root": str(self.example)})
        files = srv._scan_files(self.example, cfg.scan_roots, 2500)
        built = srv._build_context_docs(
            self.example,
            files,
            previous={},
            cfg=cfg,
        )
        index_path = Path(built["documents"]["index_json"])
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertIn("operational_profile", index)
        op = index.get("operational_profile") or {}
        self.assertIn("ui_interaction_model", op)
        self.assertIn("gameplay_understanding", op)

        result = srv._tool_design_game_basic_test_flow(
            ctx,
            {"project_root": str(self.example), "flow_id": "unittest_phased", "flow_name": "unittest"},
        )
        self.assertEqual(result.get("status"), "generated")
        gen = result.get("generation_evidence") or {}
        self.assertTrue(gen.get("phased_generation"))
        enter = (gen.get("selected_steps") or {}).get("enter_game") or {}
        self.assertIn("StartButton", str(enter.get("candidate_id", "")))
        fa1 = (gen.get("selected_steps") or {}).get("feature_action_1") or {}
        self.assertIn("ModeButton", str(fa1.get("candidate_id", "")))


if __name__ == "__main__":
    unittest.main()
