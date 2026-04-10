"""Unit tests for MCP hard_teardown / optional Godot process termination helpers."""

from __future__ import annotations

import json
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

    def test_annotate_project_close_flags_stale_execution_report(self) -> None:
        close_meta: dict = {
            "acknowledged": True,
            "play_running_by_runtime_gate": False,
        }
        rep = {"runtime_mode": "play_mode", "runtime_gate_passed": True}
        mcp_server._annotate_project_close_vs_execution_report(close_meta, rep)
        self.assertTrue(close_meta.get("stale_execution_report_runtime_fields"))
        self.assertIn("execution_report.runtime_mode", str(close_meta.get("stale_execution_report_note", "")))

    def test_annotate_project_close_skips_when_no_mismatch(self) -> None:
        close_meta: dict = {"play_running_by_runtime_gate": False}
        mcp_server._annotate_project_close_vs_execution_report(
            close_meta, {"runtime_mode": "editor_bridge", "runtime_gate_passed": False}
        )
        self.assertNotIn("stale_execution_report_runtime_fields", close_meta)

    def test_read_teardown_debug_game_artifact_and_close_meta(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "proj"
            art = root / "pointer_gpf" / "tmp" / "teardown_debug_game_last.json"
            art.parent.mkdir(parents=True, exist_ok=True)
            art.write_text(
                json.dumps(
                    {"schema": "pointer_gpf.teardown_debug_game.v1", "ok": False, "reason": "unit_test_reason"},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            got = mcp_server._read_teardown_debug_game_artifact(root)
            self.assertFalse(got.get("ok"))
            close_meta: dict = {}
            mcp_server._attach_teardown_debug_game_artifact_to_close_meta(root, close_meta)
            self.assertIn("debug_game_teardown_ok", close_meta)
            self.assertIs(close_meta.get("debug_game_teardown_ok"), False)
            self.assertEqual(close_meta.get("debug_game_teardown_reason"), "unit_test_reason")

    def test_attach_teardown_success_artifact(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "proj"
            art = root / "pointer_gpf" / "tmp" / "teardown_debug_game_last.json"
            art.parent.mkdir(parents=True, exist_ok=True)
            art.write_text(
                json.dumps(
                    {
                        "schema": "pointer_gpf.teardown_debug_game.v1",
                        "ok": True,
                        "reason": "stop_playing_scene_completed",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            close_meta: dict = {}
            mcp_server._attach_teardown_debug_game_artifact_to_close_meta(root, close_meta)
            self.assertTrue(close_meta.get("debug_game_teardown_ok"))
            self.assertIn("pointer_gpf.teardown_debug_game", str(close_meta.get("debug_game_teardown_schema", "")))

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

    @mock.patch.object(mcp_server, "_force_terminate_godot_processes_holding_project")
    def test_hard_teardown_force_when_acked_but_play_still_running(self, mock_ft: mock.MagicMock) -> None:
        mock_ft.return_value = {"outcome": "terminated", "pids": [9001], "detail": ""}
        root = Path("D:/proj/x")
        ht = mcp_server._hard_teardown_for_flow_failure(
            root,
            {"force_terminate_godot_on_flow_failure": True},
            {
                "requested": True,
                "acknowledged": True,
                "play_running_by_runtime_gate": True,
            },
        )
        self.assertTrue(ht["force_terminate_godot"]["attempted"])
        self.assertEqual(ht["force_terminate_godot"]["outcome"], "terminated")
        mock_ft.assert_called_once_with(root)

    def test_issue_from_flow_app_error_prefers_suggestion(self) -> None:
        exc = mcp_server.AppError(
            "TIMEOUT",
            "msg",
            {"auto_fix_arguments_suggestion": {"issue": "use this", "max_cycles": 3}},
        )
        self.assertEqual(mcp_server._issue_text_from_flow_app_error(exc), "use this")


class TestPostAckPlayStillRunning(unittest.TestCase):
    def test_second_close_when_gate_still_play_after_ack(self) -> None:
        calls = {"n": 0}

        def fake_once(root: Path, *, timeout_ms: int) -> dict:
            calls["n"] += 1
            return {"requested": True, "acknowledged": True, "timeout_ms": timeout_ms, "message": "ack"}

        gate_states = [
            {"runtime_mode": "play_mode", "runtime_gate_passed": True},
            {"runtime_mode": "play_mode", "runtime_gate_passed": True},
            {"runtime_mode": "editor_bridge", "runtime_gate_passed": False},
        ]
        idx = {"i": 0}

        def fake_read_gate(_root: Path) -> dict:
            j = min(idx["i"], len(gate_states) - 1)
            g = gate_states[j]
            idx["i"] += 1
            return g

        root = Path("/tmp/pointer_gpf_fake_project")
        with mock.patch.object(mcp_server, "_request_project_close_once", side_effect=fake_once):
            with mock.patch.object(mcp_server, "_read_runtime_gate_marker", side_effect=fake_read_gate):
                out = mcp_server._request_project_close_until_gate_quiescent(
                    root,
                    timeout_ms_per_attempt=100,
                    max_attempts=3,
                    post_ack_gate_deadline_s=0.0,
                    post_ack_poll_interval_s=0.001,
                    post_ack_max_extra_close_rounds=2,
                )
        self.assertTrue(out.get("acknowledged"))
        self.assertGreaterEqual(calls["n"], 2, "should issue another close when gate still implies playing")


if __name__ == "__main__":
    unittest.main()
