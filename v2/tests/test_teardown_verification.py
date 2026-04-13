from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.teardown_verification import acquire_flow_lock, release_flow_lock, verify_teardown


class TeardownVerificationTests(unittest.TestCase):
    def test_verify_teardown_passes_when_play_stopped_and_single_process(self) -> None:
        project_root = Path.cwd()
        ticks = iter([0.0, 0.0, 0.1, 0.2, 0.4, 0.6])
        result = verify_teardown(
            project_root,
            read_runtime_gate=lambda _: {"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
            list_project_editor_processes=lambda _: [{"ProcessId": 1234, "Name": "Godot.exe", "CommandLine": "godot -e"}],
            monotonic=lambda: next(ticks),
            sleep=lambda _: None,
            timeout_ms=1000,
            stable_ms=300,
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["project_process_count"], 1)

    def test_verify_teardown_waits_for_stable_stop_window(self) -> None:
        project_root = Path.cwd()
        gate_values = iter(
            [
                {"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
                {"runtime_gate_passed": True, "runtime_mode": "play_mode"},
                {"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
                {"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
                {"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
            ]
        )
        ticks = iter([0.0, 0.0, 0.1, 0.15, 0.25, 0.45, 0.65, 0.85, 1.05])
        result = verify_teardown(
            project_root,
            read_runtime_gate=lambda _: next(gate_values),
            list_project_editor_processes=lambda _: [{"ProcessId": 1234, "Name": "Godot.exe", "CommandLine": "godot -e"}],
            monotonic=lambda: next(ticks),
            sleep=lambda _: None,
            timeout_ms=1000,
            stable_ms=200,
        )
        self.assertEqual(result["status"], "verified")
        self.assertGreaterEqual(result["stable_stop_ms"], 200)

    def test_verify_teardown_fails_when_multiple_project_processes_remain(self) -> None:
        project_root = Path.cwd()
        ticks = iter([0.0, 0.0, 0.1, 1.0])
        result = verify_teardown(
            project_root,
            read_runtime_gate=lambda _: {"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
            list_project_editor_processes=lambda _: [
                {"ProcessId": 1234, "Name": "Godot.exe", "CommandLine": "godot -e --path project"},
                {"ProcessId": 5678, "Name": "Godot.exe", "CommandLine": "godot -e --path project"},
            ],
            monotonic=lambda: next(ticks),
            sleep=lambda _: None,
            timeout_ms=50,
            stable_ms=25,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["project_process_count"], 2)

    def test_acquire_and_release_flow_lock_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            lock_dir = project_root / "pointer_gpf" / "tmp"
            make_path = lambda root: lock_dir / "flow_run.lock"
            read_lock = lambda root: {} if not make_path(root).exists() else {"token": "token"}
            lock = acquire_flow_lock(
                project_root,
                flow_lock_path=make_path,
                read_flow_lock=lambda root: {} if not make_path(root).exists() else {"token": "token", "pid": 1},
                is_pid_running=lambda _: False,
            )
            self.assertTrue(make_path(project_root).exists())
            release_flow_lock(
                project_root,
                lock["token"],
                flow_lock_path=make_path,
                read_flow_lock=lambda root: lock if make_path(root).exists() else {},
            )
            self.assertFalse(make_path(project_root).exists())

    def test_acquire_flow_lock_recovers_stale_lock_when_pid_is_dead(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            make_path = lambda root: Path(tmp) / "pointer_gpf" / "tmp" / "flow_run.lock"
            lock_path = make_path(project_root)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text('{"schema":"pointer_gpf.v2.flow_lock.v1","pid":999999,"token":"stale-token"}', encoding="utf-8")

            lock = acquire_flow_lock(
                project_root,
                flow_lock_path=make_path,
                read_flow_lock=lambda root: {"schema": "pointer_gpf.v2.flow_lock.v1", "pid": 999999, "token": "stale-token"},
                is_pid_running=lambda _: False,
            )

        self.assertTrue(lock["recovered_stale_lock"])
        self.assertEqual(lock["stale_lock"]["token"], "stale-token")


if __name__ == "__main__":
    unittest.main()
