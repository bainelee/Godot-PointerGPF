"""Tests for remediation_handlers registry and server-registered handlers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import remediation_handlers as rh  # noqa: E402


class TestRemediationHandlers(unittest.TestCase):
    def test_unknown_class_returns_not_handled(self) -> None:
        out = rh.run_handlers("definitely_not_registered", object(), Path("."), {}, {})
        self.assertFalse(out["handled"])
        self.assertIn("no handler", out["notes"].lower())

    def test_custom_registered_handler_runs(self) -> None:
        calls: list[str] = []

        def h(ctx, pr, ta, d):
            calls.append("x")
            return {"handled": True, "actions": [], "notes": "ok"}

        rh.register_handler("custom_test_class", h)
        self.addCleanup(rh._REGISTRY.pop, "custom_test_class", None)  # noqa: SLF001
        out = rh.run_handlers("custom_test_class", None, Path("/tmp"), {}, {})
        self.assertTrue(out["handled"])
        self.assertEqual(calls, ["x"])


class TestServerRemediationHandlers(unittest.TestCase):
    @mock.patch("server._tool_refresh_project_context")
    @mock.patch("server._tool_update_game_basic_design_flow_by_current_state")
    def test_flow_generation_blocked_calls_refresh(
        self, mock_upd: mock.MagicMock, mock_ref: mock.MagicMock
    ) -> None:
        import server as srv  # noqa: E402

        mock_ref.return_value = {"status": "ok"}
        mock_upd.return_value = {"flow_result": {"status": "blocked"}}
        ctx = mock.MagicMock()
        out = srv._remediation_handler_flow_generation_blocked(ctx, Path("/tmp/p"), {}, {})
        mock_ref.assert_called_once()
        mock_upd.assert_called_once()
        self.assertFalse(out["handled"])

    @mock.patch("server._ensure_runtime_play_mode")
    def test_runtime_gate_handler_marks_handled_when_gate_passes(
        self, mock_gate: mock.MagicMock
    ) -> None:
        import server as srv  # noqa: E402

        mock_gate.return_value = ({"runtime_gate_passed": True}, {"launch_attempted": False})
        ctx = mock.MagicMock()
        out = srv._remediation_handler_runtime_gate(ctx, Path("/tmp/p"), {}, {})
        self.assertTrue(out["handled"])


if __name__ == "__main__":
    unittest.main()
