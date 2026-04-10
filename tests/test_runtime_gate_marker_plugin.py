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
        self.assertIn("_remove_auto_stop_play_flag_on_editor_load", content)
        self.assertIn("issued_at_unix", content)
        self.assertIn("_STOP_FLAG_MAX_AGE_SEC", content)
        self.assertIn("_STOP_FLAG_MAX_CLOCK_SKEW_SEC", content)
        self.assertIn("_was_playing_scene", content)
        self.assertIn("_deferred_chain_stop_debug_game_session", content)

    def test_auto_stop_play_polled_before_gate_sync_throttle(self) -> None:
        """closeProject stop flag must not wait for the 200ms gate sync tick (Task 4 teardown plan)."""
        repo_root = Path(__file__).resolve().parents[1]
        plugin_file = repo_root / "godot_plugin_template" / "addons" / "pointer_gpf" / "plugin.gd"
        content = plugin_file.read_text(encoding="utf-8")
        process_body = content.split("func _process", 1)[1].split("func _exit_tree", 1)[0]
        marker = (
            "_handle_auto_stop_play_request()\n\n    _gate_sync_accum += delta"
        )
        self.assertIn(
            marker,
            process_body,
            msg="expected _handle_auto_stop_play_request before _gate_sync_accum in _process",
        )
        self.assertEqual(
            process_body.count("_handle_auto_stop_play_request()"),
            1,
            msg="_process should call _handle_auto_stop_play_request exactly once (not only inside 0.2s gate)",
        )


if __name__ == "__main__":
    unittest.main()
