from __future__ import annotations

import unittest
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


_ADDON_REL = Path("addons") / "test_orchestrator"

_EXPECTED_FILES = (
    "flow_timeline_utils.gd",
    "flow_timeline_utils.gd.uid",
    "plugin.cfg",
    "plugin.gd",
    "plugin.gd.uid",
    "plugin_history_controller.gd",
    "plugin_history_controller.gd.uid",
    "plugin_live_flow_controller.gd",
    "plugin_live_flow_controller.gd.uid",
    "plugin_ui_builder.gd",
    "plugin_ui_builder.gd.uid",
)


class GodotTestOrchestratorPackagingTests(unittest.TestCase):
    def test_addon_tree_files_exist(self) -> None:
        root = _repo_root()
        base = root / _ADDON_REL
        self.assertTrue(base.is_dir(), msg=f"缺少目录 {_ADDON_REL.as_posix()}")
        for name in _EXPECTED_FILES:
            path = base / name
            self.assertTrue(path.is_file(), msg=f"缺少文件 {(_ADDON_REL / name).as_posix()}")

    def test_plugin_cfg_name_and_script(self) -> None:
        cfg = _repo_root() / _ADDON_REL / "plugin.cfg"
        text = cfg.read_text(encoding="utf-8")
        self.assertIn('name="Test Orchestrator"', text)
        self.assertIn('script="plugin.gd"', text)

    def test_plugin_gd_editor_plugin_entry(self) -> None:
        gd = _repo_root() / _ADDON_REL / "plugin.gd"
        text = gd.read_text(encoding="utf-8")
        self.assertIn("@tool", text)
        self.assertIn("extends EditorPlugin", text)

    def test_godot_minimal_enables_test_orchestrator(self) -> None:
        proj = _repo_root() / "examples" / "godot_minimal" / "project.godot"
        text = proj.read_text(encoding="utf-8")
        self.assertIn("res://addons/test_orchestrator/plugin.cfg", text)


if __name__ == "__main__":
    unittest.main()
