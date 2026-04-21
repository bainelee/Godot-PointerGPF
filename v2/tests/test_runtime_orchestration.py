from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.runtime_orchestration import (
    normalize_execution_mode,
    resolve_requested_flow_file,
    run_basic_flow_tool,
)
from v2.mcp_core.flow_runner import FlowExecutionStepFailed


class RuntimeOrchestrationTests(unittest.TestCase):
    def test_normalize_execution_mode_rejects_unknown_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported execution mode"):
            normalize_execution_mode("desktop_magic")

    def test_resolve_requested_flow_file_returns_stale_error_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)

            flow_file, early_response, basicflow_context = resolve_requested_flow_file(
                project_root,
                None,
                allow_stale_basicflow=False,
                detect_basicflow_staleness=lambda _: {"status": "stale", "flow_summary": "summary"},
                load_basicflow_assets=lambda _: {"paths": {"flow_file": str(project_root / "pointer_gpf" / "basicflow.json")}},
            )

        self.assertIsNone(flow_file)
        self.assertIsNotNone(early_response)
        self.assertIsNone(basicflow_context)
        assert early_response is not None
        self.assertEqual(early_response["error"]["code"], "BASICFLOW_STALE")

    def test_run_basic_flow_tool_supports_isolated_runtime_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "pointer_gpf" / "basicflow.json"
            flow_file.parent.mkdir(parents=True, exist_ok=True)
            flow_file.write_text(
                json.dumps({"flowId": "project_basicflow", "steps": [{"id": "close", "action": "closeProject"}]}),
                encoding="utf-8",
            )
            isolated_session = type(
                "Session",
                (),
                {
                    "pid": 4321,
                    "desktop_name": "pointer_gpf_v2_test",
                    "host_desktop_name": "Default",
                    "process": object(),
                },
            )()

            exit_code, response, _ = run_basic_flow_tool(
                project_root,
                flow_file,
                basicflow_context={"status": "fresh", "flow_summary": "summary"},
                execution_mode="isolated_runtime",
                load_flow=lambda _: {"flowId": "project_basicflow", "steps": [{"id": "close", "action": "closeProject"}]},
                sync_project_plugin=lambda _: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda _: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                detect_multiple_project_processes=lambda _: None,
                acquire_flow_lock=lambda _: {"token": "token", "recovered_stale_lock": False},
                ensure_play_mode=lambda _: {"status": "entered_play_mode"},
                launch_isolated_runtime=lambda _root, _exe: isolated_session,
                load_godot_executable=lambda _: "D:/GODOT/Godot.exe",
                run_basic_flow=lambda _root, _flow: {"status": "passed", "step_count": 1},
                verify_isolated_runtime_stopped=lambda _: {"status": "verified", "runtime_pid": 4321},
                verify_teardown=lambda _: {"status": "verified", "project_process_count": 0},
                terminate_project_processes=lambda _: {"status": "cleared", "terminated_pids": [], "remaining_process_count": 0},
                clear_runtime_markers=lambda _: None,
                mark_basicflow_run_success=lambda _: {"last_successful_run_at": "2026-04-11T12:34:56+00:00"},
                basicflow_paths=lambda _: type("Paths", (), {"flow_file": flow_file})(),
                close_isolated_runtime_session=lambda _: None,
                release_flow_lock=lambda _root, _token: None,
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["execution_mode"], "isolated_runtime")
        self.assertTrue(response["result"]["isolation"]["isolated"])

    def test_run_basic_flow_tool_marks_project_basicflow_run_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "pointer_gpf" / "basicflow.json"
            flow_file.parent.mkdir(parents=True, exist_ok=True)
            flow_file.write_text(
                json.dumps({"flowId": "project_basicflow", "steps": [{"id": "close", "action": "closeProject"}]}),
                encoding="utf-8",
            )

            exit_code, response, _ = run_basic_flow_tool(
                project_root,
                flow_file,
                basicflow_context={"status": "fresh", "flow_summary": "summary"},
                execution_mode="play_mode",
                load_flow=lambda _: {"flowId": "project_basicflow", "steps": [{"id": "close", "action": "closeProject"}]},
                sync_project_plugin=lambda _: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda _: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                detect_multiple_project_processes=lambda _: None,
                acquire_flow_lock=lambda _: {"token": "token", "recovered_stale_lock": False},
                ensure_play_mode=lambda _: {"status": "entered_play_mode"},
                launch_isolated_runtime=lambda _root, _exe: None,
                load_godot_executable=lambda _: "D:/GODOT/Godot.exe",
                run_basic_flow=lambda _root, _flow: {"status": "passed", "step_count": 1},
                verify_isolated_runtime_stopped=lambda _: {"status": "verified"},
                verify_teardown=lambda _: {"status": "verified", "project_process_count": 0},
                terminate_project_processes=lambda _: {"status": "cleared", "terminated_pids": [1234], "remaining_process_count": 0},
                clear_runtime_markers=lambda _: None,
                mark_basicflow_run_success=lambda _: {"last_successful_run_at": "2026-04-11T12:34:56+00:00"},
                basicflow_paths=lambda _: type("Paths", (), {"flow_file": flow_file})(),
                close_isolated_runtime_session=lambda _: None,
                release_flow_lock=lambda _root, _token: None,
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["basicflow"]["last_successful_run_at"], "2026-04-11T12:34:56+00:00")
        self.assertFalse(response["result"]["isolation"]["isolated"])
        self.assertEqual(response["result"]["project_close"]["project_process_count"], 0)

    def test_run_basic_flow_tool_cleans_up_current_project_on_step_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "pointer_gpf" / "basicflow.json"
            flow_file.parent.mkdir(parents=True, exist_ok=True)
            flow_file.write_text(
                json.dumps({"flowId": "project_basicflow", "steps": [{"id": "close", "action": "closeProject"}]}),
                encoding="utf-8",
            )
            cleanup_called: list[str] = []

            exit_code, response, success = run_basic_flow_tool(
                project_root,
                flow_file,
                execution_mode="play_mode",
                load_flow=lambda _: {"flowId": "project_basicflow", "steps": [{"id": "close", "action": "closeProject"}]},
                sync_project_plugin=lambda _: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda _: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                detect_multiple_project_processes=lambda _: None,
                acquire_flow_lock=lambda _: {"token": "token", "recovered_stale_lock": False},
                ensure_play_mode=lambda _: {"status": "entered_play_mode"},
                launch_isolated_runtime=lambda _root, _exe: None,
                load_godot_executable=lambda _: "D:/GODOT/Godot.exe",
                run_basic_flow=lambda _root, _flow: (_ for _ in ()).throw(
                    FlowExecutionStepFailed("step failed", step_index=2, step_id="click_start", run_id="run-1")
                ),
                verify_isolated_runtime_stopped=lambda _: {"status": "verified"},
                verify_teardown=lambda _: {"status": "verified", "project_process_count": 0},
                terminate_project_processes=lambda _: cleanup_called.append("kill") or {
                    "status": "cleared",
                    "terminated_pids": [1234],
                    "remaining_process_count": 0,
                },
                clear_runtime_markers=lambda _: cleanup_called.append("clear"),
                mark_basicflow_run_success=lambda _: {"last_successful_run_at": ""},
                basicflow_paths=lambda _: type("Paths", (), {"flow_file": flow_file})(),
                close_isolated_runtime_session=lambda _: None,
                release_flow_lock=lambda _root, _token: None,
            )

        self.assertEqual(exit_code, 2)
        self.assertFalse(success)
        self.assertFalse(response["ok"])
        self.assertEqual(cleanup_called, ["kill", "clear"])
        self.assertEqual(response["error"]["details"]["project_close"]["project_process_count"], 0)

    def test_run_basic_flow_tool_cleans_up_when_ensure_play_mode_times_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "pointer_gpf" / "basicflow.json"
            flow_file.parent.mkdir(parents=True, exist_ok=True)
            flow_file.write_text(
                json.dumps({"flowId": "project_basicflow", "steps": [{"id": "close", "action": "closeProject"}]}),
                encoding="utf-8",
            )
            cleanup_called: list[str] = []

            exit_code, response, success = run_basic_flow_tool(
                project_root,
                flow_file,
                execution_mode="play_mode",
                load_flow=lambda _: {"flowId": "project_basicflow", "steps": [{"id": "close", "action": "closeProject"}]},
                sync_project_plugin=lambda _: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda _: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                detect_multiple_project_processes=lambda _: None,
                acquire_flow_lock=lambda _: {"token": "token", "recovered_stale_lock": False},
                ensure_play_mode=lambda _: (_ for _ in ()).throw(TimeoutError("play mode was not entered within 15000 ms")),
                launch_isolated_runtime=lambda _root, _exe: None,
                load_godot_executable=lambda _: "D:/GODOT/Godot.exe",
                run_basic_flow=lambda _root, _flow: {"status": "passed", "step_count": 1},
                verify_isolated_runtime_stopped=lambda _: {"status": "verified"},
                verify_teardown=lambda _: {"status": "verified", "project_process_count": 0},
                terminate_project_processes=lambda _: cleanup_called.append("kill") or {
                    "status": "cleared",
                    "terminated_pids": [1234],
                    "remaining_process_count": 0,
                },
                clear_runtime_markers=lambda _: cleanup_called.append("clear"),
                mark_basicflow_run_success=lambda _: {"last_successful_run_at": ""},
                basicflow_paths=lambda _: type("Paths", (), {"flow_file": flow_file})(),
                close_isolated_runtime_session=lambda _: None,
                release_flow_lock=lambda _root, _token: None,
            )

        self.assertEqual(exit_code, 2)
        self.assertFalse(success)
        self.assertFalse(response["ok"])
        self.assertEqual(cleanup_called, ["kill", "clear"])
        self.assertEqual(response["error"]["details"]["project_close"]["project_process_count"], 0)


if __name__ == "__main__":
    unittest.main()
