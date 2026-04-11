import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.plugin_sync import sync_plugin


class PluginSyncTests(unittest.TestCase):
    def test_sync_plugin_enables_editor_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            plugin_root = root / "plugin" / "addons" / "pointer_gpf"
            project_root.mkdir(parents=True)
            plugin_root.mkdir(parents=True)
            (project_root / "project.godot").write_text("[application]\nconfig/name=\"Test\"\n", encoding="utf-8")
            (plugin_root / "plugin.cfg").write_text("[plugin]\nname=\"x\"\n", encoding="utf-8")
            (plugin_root / "plugin.gd").write_text("@tool\nextends EditorPlugin\n", encoding="utf-8")
            sync_plugin(plugin_root, project_root)
            content = (project_root / "project.godot").read_text(encoding="utf-8")
            self.assertIn('[editor_plugins]', content)
            self.assertIn('enabled=PackedStringArray("res://addons/pointer_gpf/plugin.cfg")', content)


if __name__ == "__main__":
    unittest.main()
