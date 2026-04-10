"""Unit tests for MCP hard_teardown / optional Godot process termination helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import server as mcp_server  # noqa: E402


class TestHardTeardownHelpers(unittest.TestCase):
    def test_runtime_gate_implies_playing(self) -> None:
        self.assertIsNone(mcp_server._runtime_gate_implies_playing({}))
        self.assertTrue(mcp_server._runtime_gate_implies_playing({"runtime_mode": "play_mode", "runtime_gate_passed": True}))
        self.assertFalse(
            mcp_server._runtime_gate_implies_playing({"runtime_mode": "editor_bridge", "runtime_gate_passed": False})
        )

    def test_hard_teardown_close_not_acked_default_no_force(self) -> None:
        root = Path("D:/proj/x")
        ht = mcp_server._hard_teardown_for_flow_failure(
            root,
            {},
            {"requested": True, "acknowledged": False},
        )
        self.assertTrue(ht["user_must_check_engine_process"])
        self.assertEqual(ht["force_terminate_godot"]["outcome"], "disabled_by_default")
        self.assertFalse(ht["force_terminate_godot"]["attempted"])

    @mock.patch.object(mcp_server, "_force_terminate_godot_processes_holding_project")
    def test_hard_teardown_force_runs_kill_helper(self, mock_ft: mock.MagicMock) -> None:
        mock_ft.return_value = {"outcome": "terminated", "pids": [4242], "detail": ""}
        root = Path("D:/proj/x")
        ht = mcp_server._hard_teardown_for_flow_failure(
            root,
            {"force_terminate_godot_on_flow_failure": True},
            {"requested": True, "acknowledged": False},
        )
        self.assertTrue(ht["force_terminate_godot"]["attempted"])
        self.assertEqual(ht["force_terminate_godot"]["outcome"], "terminated")
        self.assertEqual(ht["force_terminate_godot"]["pids"], [4242])
        mock_ft.assert_called_once_with(root)

    def test_issue_from_flow_app_error_prefers_suggestion(self) -> None:
        exc = mcp_server.AppError(
            "TIMEOUT",
            "msg",
            {"auto_fix_arguments_suggestion": {"issue": "use this", "max_cycles": 3}},
        )
        self.assertEqual(mcp_server._issue_text_from_flow_app_error(exc), "use this")


if __name__ == "__main__":
    unittest.main()
