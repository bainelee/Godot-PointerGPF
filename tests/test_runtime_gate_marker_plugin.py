from pathlib import Path
import unittest


class RuntimeGateMarkerPluginTests(unittest.TestCase):
    def test_editor_plugin_writes_runtime_gate_marker(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        plugin_file = repo_root / "godot_plugin_template" / "addons" / "pointer_gpf" / "plugin.gd"
        content = plugin_file.read_text(encoding="utf-8")

        self.assertIn("runtime_gate.json", content)
        self.assertIn("runtime_mode", content)
        self.assertIn("play_mode", content)
        self.assertIn("runtime_gate_passed", content)
        self.assertIn("auto_enter_play_mode.flag", content)
        self.assertIn("play_main_scene", content)


if __name__ == "__main__":
    unittest.main()
