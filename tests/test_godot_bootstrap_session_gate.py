"""Tests for MCP bootstrap session ack polling (editor plugin load handshake)."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))


class GodotBootstrapSessionGateTests(unittest.TestCase):
    def test_await_bootstrap_session_ack_succeeds_when_gate_updated(self) -> None:
        import server as srv

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
            bridge = root / "pointer_gpf" / "tmp"
            bridge.mkdir(parents=True)
            sid = "test-session-abc"

            def delayed_write() -> None:
                time.sleep(0.05)
                marker = bridge / "runtime_gate.json"
                marker.write_text(
                    json.dumps(
                        {
                            "runtime_mode": "editor_bridge",
                            "runtime_entry": "unknown",
                            "runtime_gate_passed": False,
                            "bootstrap_session_ack": sid,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

            threading.Thread(target=delayed_write, daemon=True).start()
            ok, last, elapsed = srv._await_bootstrap_session_ack(
                root, sid, timeout_ms=3_000, poll_ms=20
            )
            self.assertTrue(ok, msg=str(last))
            self.assertGreaterEqual(elapsed, 0.0)

    def test_await_bootstrap_session_ack_times_out(self) -> None:
        import server as srv

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
            (root / "pointer_gpf" / "tmp").mkdir(parents=True)
            ok, _last, elapsed = srv._await_bootstrap_session_ack(
                root, "never-comes", timeout_ms=80, poll_ms=10
            )
            self.assertFalse(ok)
            self.assertLessEqual(elapsed, 500.0)


if __name__ == "__main__":
    unittest.main()
