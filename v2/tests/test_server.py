import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from v2.mcp_core.server import (
    _acquire_flow_lock,
    _detect_multiple_project_processes,
    _flow_lock_path,
    _is_editor_process_running,
    _launch_editor_if_needed,
    _normalize_execution_mode,
    _release_flow_lock,
    _verify_teardown,
    main,
)


class ServerLaunchEditorTests(unittest.TestCase):
    def test_normalize_execution_mode_rejects_unknown_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported execution mode"):
            _normalize_execution_mode("desktop_magic")

    def test_is_editor_process_running_uses_unescaped_project_path_in_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            with patch("v2.mcp_core.server.subprocess.run") as run_mock:
                run_mock.return_value.stdout = json.dumps(
                    {"ProcessId": 1234, "Name": "Godot.exe", "CommandLine": f"Godot -e --path {project_root.resolve()}"}
                )
                run_mock.return_value.returncode = 0

                result = _is_editor_process_running(project_root)

        self.assertTrue(result)
        probe = run_mock.call_args.args[0][2]
        self.assertIn(str(project_root.resolve()), probe)
        self.assertNotIn("\\\\", probe)

    def test_is_editor_process_running_ignores_non_editor_runtime_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            with patch(
                "v2.mcp_core.server._list_project_processes",
                return_value=[
                    {"ProcessId": 10, "Name": "Godot.exe", "CommandLine": f"Godot --path {project_root.resolve()}"},
                ],
            ):
                result = _is_editor_process_running(project_root)

        self.assertFalse(result)

    def test_launch_editor_if_needed_reuses_running_editor_without_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text("[application]\nconfig/name=\"tmp\"\n", encoding="utf-8")

            with patch("v2.mcp_core.server._is_editor_process_running", return_value=True), patch(
                "v2.mcp_core.server.subprocess.Popen"
            ) as popen_mock:
                result = _launch_editor_if_needed(project_root)

        self.assertEqual(result["status"], "editor_running")
        self.assertEqual(result["runtime_gate"], {})
        popen_mock.assert_not_called()

    def test_launch_editor_if_needed_reuses_running_editor_with_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            gate_path = project_root / "pointer_gpf" / "tmp" / "runtime_gate.json"
            gate_path.parent.mkdir(parents=True, exist_ok=True)
            gate_payload = {"runtime_gate_passed": False, "runtime_mode": "editor_poll"}
            gate_path.write_text(json.dumps(gate_payload), encoding="utf-8")

            with patch("v2.mcp_core.server._is_editor_process_running", return_value=True), patch(
                "v2.mcp_core.server.subprocess.Popen"
            ) as popen_mock:
                result = _launch_editor_if_needed(project_root)

        self.assertEqual(result["status"], "already_available")
        self.assertEqual(result["runtime_gate"], gate_payload)
        popen_mock.assert_not_called()

    def test_verify_teardown_passes_when_play_stopped_and_single_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            with patch(
                "v2.mcp_core.server._read_runtime_gate",
                return_value={"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
            ), patch(
                "v2.mcp_core.server._list_project_processes",
                return_value=[{"ProcessId": 1234, "Name": "Godot.exe", "CommandLine": "godot -e"}],
            ), patch(
                "v2.mcp_core.server.time.monotonic",
                side_effect=[0.0, 0.0, 0.1, 0.2, 0.4, 0.6],
            ), patch("v2.mcp_core.server.time.sleep"):
                result = _verify_teardown(project_root, timeout_ms=1000, stable_ms=300)

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["project_process_count"], 1)
        self.assertGreaterEqual(result["stable_stop_ms"], 300)

    def test_verify_teardown_waits_for_stable_stop_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            with patch(
                "v2.mcp_core.server._read_runtime_gate",
                side_effect=[
                    {"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
                    {"runtime_gate_passed": True, "runtime_mode": "play_mode"},
                    {"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
                    {"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
                    {"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
                ],
            ), patch(
                "v2.mcp_core.server._list_project_processes",
                return_value=[{"ProcessId": 1234, "Name": "Godot.exe", "CommandLine": "godot -e"}],
            ), patch(
                "v2.mcp_core.server.time.monotonic",
                side_effect=[0.0, 0.0, 0.1, 0.15, 0.25, 0.45, 0.65, 0.85, 1.05],
            ), patch("v2.mcp_core.server.time.sleep"):
                result = _verify_teardown(project_root, timeout_ms=1000, stable_ms=200)

        self.assertEqual(result["status"], "verified")
        self.assertGreaterEqual(result["stable_stop_ms"], 200)

    def test_verify_teardown_fails_when_multiple_project_processes_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            with patch(
                "v2.mcp_core.server._read_runtime_gate",
                return_value={"runtime_gate_passed": False, "runtime_mode": "editor_poll"},
            ), patch(
                "v2.mcp_core.server._list_project_processes",
                return_value=[
                    {"ProcessId": 1234, "Name": "Godot.exe", "CommandLine": "godot -e --path project"},
                    {"ProcessId": 5678, "Name": "Godot.exe", "CommandLine": "godot -e --path project"},
                ],
            ), patch(
                "v2.mcp_core.server.time.monotonic",
                side_effect=[0.0, 0.0, 0.1, 1.0],
            ), patch("v2.mcp_core.server.time.sleep"):
                result = _verify_teardown(project_root, timeout_ms=50, stable_ms=25)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["project_process_count"], 2)

    def test_acquire_flow_lock_writes_lock_and_release_removes_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)

            lock = _acquire_flow_lock(project_root)
            lock_path = _flow_lock_path(project_root)

            self.assertTrue(lock_path.is_file())
            self.assertEqual(json.loads(lock_path.read_text(encoding="utf-8"))["token"], lock["token"])

            _release_flow_lock(project_root, lock["token"])

            self.assertFalse(lock_path.exists())

    def test_acquire_flow_lock_recovers_stale_lock_when_pid_is_dead(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            lock_path = _flow_lock_path(project_root)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps({"schema": "pointer_gpf.v2.flow_lock.v1", "pid": 999999, "token": "stale-token"}),
                encoding="utf-8",
            )

            with patch("v2.mcp_core.server._is_pid_running", return_value=False):
                lock = _acquire_flow_lock(project_root)

            self.assertTrue(lock["recovered_stale_lock"])
            self.assertEqual(lock["stale_lock"]["token"], "stale-token")
            self.assertEqual(json.loads(lock_path.read_text(encoding="utf-8"))["token"], lock["token"])

    def test_detect_multiple_project_processes_reports_manual_multi_editor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            with patch(
                "v2.mcp_core.server._list_project_processes",
                return_value=[
                    {"ProcessId": 1, "Name": "Godot.exe", "CommandLine": "godot -e --path a"},
                    {"ProcessId": 2, "Name": "Godot.exe", "CommandLine": "godot -e --path a"},
                ],
            ):
                result = _detect_multiple_project_processes(project_root)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["project_process_count"], 2)

    def test_main_run_basic_flow_rejects_when_lock_already_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "flow.json"
            flow_file.write_text(
                json.dumps({"flowId": "interactive", "steps": [{"id": "close", "action": "closeProject"}]}),
                encoding="utf-8",
            )
            lock_path = _flow_lock_path(project_root)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps({"schema": "pointer_gpf.v2.flow_lock.v1", "pid": os.getpid(), "token": "busy"}),
                encoding="utf-8",
            )
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "run_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": str(flow_file),
                        "godot_executable": None,
                        "plugin_source": None,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server._sync_project_plugin",
                return_value=project_root / "addons" / "pointer_gpf",
            ), patch(
                "v2.mcp_core.server.run_preflight",
                return_value=type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "FLOW_ALREADY_RUNNING")

    def test_main_run_basic_flow_without_flow_file_returns_missing_basicflow_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "run_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "missing", "is_stale": False, "reasons": [], "message": "missing"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "BASICFLOW_MISSING")
        self.assertEqual(len(payload["error"]["details"]["generation_questions"]), 3)

    def test_main_run_basic_flow_without_flow_file_returns_stale_basicflow_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "run_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={
                    "status": "stale",
                    "is_stale": True,
                    "reasons": [{"code": "BASICFLOW_RELATED_FILE_CHANGED"}],
                    "message": "stale",
                    "flow_summary": "summary",
                },
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "BASICFLOW_STALE")
        self.assertEqual(len(payload["error"]["details"]["choices"]), 4)

    def test_main_run_basic_flow_without_flow_file_can_run_stale_basicflow_when_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "pointer_gpf" / "basicflow.json"
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "run_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": True,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={
                    "status": "stale",
                    "is_stale": True,
                    "reasons": [{"code": "BASICFLOW_RELATED_FILE_CHANGED"}],
                    "message": "stale",
                    "flow_summary": "summary",
                },
            ), patch(
                "v2.mcp_core.server.load_basicflow_assets",
                return_value={"paths": {"flow_file": str(flow_file), "meta_file": str(project_root / "pointer_gpf" / "basicflow.meta.json")}},
            ), patch(
                "v2.mcp_core.server._run_basic_flow_tool",
                return_value=(0, {"ok": True, "result": {"execution": {"status": "passed"}}}, True),
            ) as run_tool_mock, redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(run_tool_mock.call_args.kwargs["basicflow_context"]["status"], "stale")

    def test_main_run_basic_flow_without_flow_file_uses_project_basicflow_when_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "pointer_gpf" / "basicflow.json"
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "run_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), patch(
                "v2.mcp_core.server.load_basicflow_assets",
                return_value={"paths": {"flow_file": str(flow_file), "meta_file": str(project_root / "pointer_gpf" / "basicflow.meta.json")}},
            ), patch(
                "v2.mcp_core.server._run_basic_flow_tool",
                return_value=(0, {"ok": True, "result": {"execution": {"status": "passed"}}}, True),
            ) as run_tool_mock, redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["execution"]["status"], "passed")
        self.assertEqual(run_tool_mock.call_args.args[1], flow_file)

    def test_run_basic_flow_tool_marks_project_basicflow_run_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "pointer_gpf" / "basicflow.json"
            flow_file.parent.mkdir(parents=True, exist_ok=True)
            flow_file.write_text(
                json.dumps({"flowId": "project_basicflow", "steps": [{"id": "close", "action": "closeProject"}]}),
                encoding="utf-8",
            )
            with patch(
                "v2.mcp_core.server._sync_project_plugin",
                return_value=project_root / "addons" / "pointer_gpf",
            ) as sync_mock, patch(
                "v2.mcp_core.server.run_preflight",
                return_value=type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
            ), patch(
                "v2.mcp_core.server._ensure_play_mode",
                return_value={"status": "entered_play_mode"},
            ), patch(
                "v2.mcp_core.server.run_basic_flow",
                return_value={"status": "passed", "step_count": 1},
            ), patch(
                "v2.mcp_core.server._verify_teardown",
                return_value={"status": "verified", "project_process_count": 1},
            ), patch(
                "v2.mcp_core.server._list_project_processes",
                return_value=[],
            ), patch(
                "v2.mcp_core.server.mark_basicflow_run_success",
                return_value={"last_successful_run_at": "2026-04-11T12:34:56+00:00"},
            ) as mark_mock:
                from v2.mcp_core.server import _run_basic_flow_tool

                exit_code, response, _ = _run_basic_flow_tool(
                    project_root,
                    flow_file,
                    basicflow_context={"status": "fresh", "flow_summary": "summary"},
                )

        self.assertEqual(exit_code, 0)
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["basicflow"]["last_successful_run_at"], "2026-04-11T12:34:56+00:00")
        self.assertFalse(response["result"]["isolation"]["isolated"])
        self.assertEqual(response["result"]["isolation"]["status"], "shared_desktop")
        self.assertEqual(response["result"]["plugin_sync"]["destination"], str(project_root / "addons" / "pointer_gpf"))
        sync_mock.assert_called_once_with(project_root)
        mark_mock.assert_called_once()

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
            with patch(
                "v2.mcp_core.server._sync_project_plugin",
                return_value=project_root / "addons" / "pointer_gpf",
            ), patch(
                "v2.mcp_core.server.run_preflight",
                return_value=type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
            ), patch(
                "v2.mcp_core.server.load_godot_executable",
                return_value="D:/GODOT/Godot_v4.6.1-stable_win64.exe/Godot_v4.6.1-stable_win64.exe",
            ), patch(
                "v2.mcp_core.server.launch_isolated_runtime",
                return_value=isolated_session,
            ), patch(
                "v2.mcp_core.server.run_basic_flow",
                return_value={"status": "passed", "step_count": 1},
            ), patch(
                "v2.mcp_core.server.verify_isolated_runtime_stopped",
                return_value={"status": "verified", "runtime_pid": 4321},
            ), patch(
                "v2.mcp_core.server.close_isolated_runtime_session",
            ) as close_mock, patch(
                "v2.mcp_core.server.mark_basicflow_run_success",
                return_value={"last_successful_run_at": "2026-04-11T12:34:56+00:00"},
            ):
                from v2.mcp_core.server import _run_basic_flow_tool

                exit_code, response, _ = _run_basic_flow_tool(
                    project_root,
                    flow_file,
                    basicflow_context={"status": "fresh", "flow_summary": "summary"},
                    execution_mode="isolated_runtime",
                )

        self.assertEqual(exit_code, 0)
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["execution_mode"], "isolated_runtime")
        self.assertTrue(response["result"]["isolation"]["isolated"])
        self.assertEqual(response["result"]["isolation"]["status"], "isolated_desktop")
        self.assertEqual(response["result"]["isolation"]["desktop_name"], "pointer_gpf_v2_test")
        self.assertEqual(response["result"]["isolation"]["host_desktop_name"], "Default")
        self.assertTrue(response["result"]["isolation"]["separate_desktop"])
        self.assertEqual(response["result"]["play_mode"]["runtime_process"]["pid"], 4321)
        self.assertEqual(response["result"]["plugin_sync"]["destination"], str(project_root / "addons" / "pointer_gpf"))
        close_mock.assert_called_once_with(isolated_session)

    def test_run_basic_flow_tool_syncs_plugin_before_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "flow.json"
            flow_file.write_text(
                json.dumps({"flowId": "interactive", "steps": [{"id": "close", "action": "closeProject"}]}),
                encoding="utf-8",
            )
            with patch(
                "v2.mcp_core.server._sync_project_plugin",
                return_value=project_root / "addons" / "pointer_gpf",
            ) as sync_mock, patch(
                "v2.mcp_core.server.run_preflight",
                return_value=type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
            ) as preflight_mock, patch(
                "v2.mcp_core.server._ensure_play_mode",
                return_value={"status": "entered_play_mode"},
            ), patch(
                "v2.mcp_core.server.run_basic_flow",
                return_value={"status": "passed", "step_count": 1},
            ), patch(
                "v2.mcp_core.server._verify_teardown",
                return_value={"status": "verified", "project_process_count": 1},
            ), patch(
                "v2.mcp_core.server._list_project_processes",
                return_value=[],
            ):
                from v2.mcp_core.server import _run_basic_flow_tool

                exit_code, response, _ = _run_basic_flow_tool(project_root, flow_file)

        self.assertEqual(exit_code, 0)
        self.assertTrue(response["ok"])
        sync_mock.assert_called_once_with(project_root)
        preflight_mock.assert_called_once_with(project_root)

    def test_main_generate_basic_flow_writes_assets_from_answers_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="scenes/main.tscn"\n',
                encoding="utf-8",
            )
            (project_root / "scenes").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")
            answer_file = project_root / "answers.json"
            answer_file.write_text(
                json.dumps(
                    {
                        "main_scene_is_entry": True,
                        "tested_features": ["进入主流程", "基础操作"],
                        "include_screenshot_evidence": True,
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "generate_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": str(answer_file),
                        "allow_stale_basicflow": False,
                    },
                )(),
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "generated")
        self.assertEqual(payload["result"]["step_count"], 6)

    def test_main_generate_basic_flow_accepts_inline_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="scenes/main.tscn"\n',
                encoding="utf-8",
            )
            (project_root / "scenes").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "generate_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                        "main_scene_is_entry": "true",
                        "tested_features": "进入主流程, 基础操作",
                        "include_screenshot_evidence": "false",
                        "entry_scene_path": None,
                    },
                )(),
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "generated")
        self.assertEqual(payload["result"]["step_count"], 5)

    def test_main_generate_basic_flow_requires_answers_file_or_inline_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "generate_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                        "main_scene_is_entry": None,
                        "tested_features": None,
                        "include_screenshot_evidence": None,
                        "entry_scene_path": None,
                    },
                )(),
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "BASICFLOW_GENERATION_ANSWERS_REQUIRED")

    def test_main_analyze_basic_flow_staleness_returns_analysis_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "analyze_basic_flow_staleness",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.analyze_basicflow_staleness",
                return_value={
                    "status": "stale",
                    "analysis_summary": "summary",
                    "recommended_next_step": "regenerate_basicflow_or_run_with_allow_stale",
                },
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "stale")

    def test_main_get_basic_flow_generation_questions_returns_question_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "get_basic_flow_generation_questions",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                        "main_scene_is_entry": None,
                        "tested_features": None,
                        "include_screenshot_evidence": None,
                        "entry_scene_path": None,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.get_basicflow_generation_questions",
                return_value={"status": "questions_ready", "question_count": 3, "questions": []},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "questions_ready")

    def test_main_start_basic_flow_generation_session_returns_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "start_basic_flow_generation_session",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                        "main_scene_is_entry": None,
                        "tested_features": None,
                        "include_screenshot_evidence": None,
                        "entry_scene_path": None,
                        "session_id": None,
                        "question_id": None,
                        "answer": None,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.start_basicflow_generation_session",
                return_value={"status": "awaiting_answer", "session_id": "abc", "next_question": {"id": "main_scene_is_entry"}},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["session_id"], "abc")

    def test_main_complete_basic_flow_generation_session_requires_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "complete_basic_flow_generation_session",
                        "project_root": str(project_root),
                        "flow_file": None,
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                        "main_scene_is_entry": None,
                        "tested_features": None,
                        "include_screenshot_evidence": None,
                        "entry_scene_path": None,
                        "session_id": None,
                        "question_id": None,
                        "answer": None,
                    },
                )(),
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 1)

    def test_main_run_basic_flow_rejects_when_multiple_editor_processes_are_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "flow.json"
            flow_file.write_text(
                json.dumps({"flowId": "interactive", "steps": [{"id": "close", "action": "closeProject"}]}),
                encoding="utf-8",
            )
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "run_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": str(flow_file),
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server._sync_project_plugin",
                return_value=project_root / "addons" / "pointer_gpf",
            ), patch(
                "v2.mcp_core.server.run_preflight",
                return_value=type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
            ), patch(
                "v2.mcp_core.server._list_project_processes",
                return_value=[
                    {"ProcessId": 11, "Name": "Godot.exe", "CommandLine": "godot -e --path project"},
                    {"ProcessId": 22, "Name": "Godot.exe", "CommandLine": "godot -e --path project"},
                ],
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "MULTIPLE_EDITOR_PROCESSES_DETECTED")

    def test_main_run_basic_flow_includes_project_close_when_teardown_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "flow.json"
            flow_file.write_text(
                json.dumps({"flowId": "interactive", "steps": [{"id": "close", "action": "closeProject"}]}),
                encoding="utf-8",
            )
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "run_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": str(flow_file),
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server._sync_project_plugin",
                return_value=project_root / "addons" / "pointer_gpf",
            ), patch(
                "v2.mcp_core.server.run_preflight",
                return_value=type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
            ), patch(
                "v2.mcp_core.server._ensure_play_mode",
                return_value={"status": "entered_play_mode"},
            ), patch(
                "v2.mcp_core.server.run_basic_flow",
                return_value={"status": "passed", "step_count": 5},
            ), patch(
                "v2.mcp_core.server._verify_teardown",
                return_value={"status": "verified", "project_process_count": 1},
            ), patch(
                "v2.mcp_core.server._list_project_processes",
                return_value=[],
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["execution"]["status"], "passed")
        self.assertEqual(payload["result"]["project_close"]["status"], "verified")
        self.assertFalse(payload["result"]["flow_guard"]["recovered_stale_lock"])

    def test_main_run_basic_flow_fails_when_teardown_verification_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            flow_file = project_root / "flow.json"
            flow_file.write_text(
                json.dumps({"flowId": "interactive", "steps": [{"id": "close", "action": "closeProject"}]}),
                encoding="utf-8",
            )
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "run_basic_flow",
                        "project_root": str(project_root),
                        "flow_file": str(flow_file),
                        "godot_executable": None,
                        "plugin_source": None,
                        "answers_file": None,
                        "allow_stale_basicflow": False,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server._sync_project_plugin",
                return_value=project_root / "addons" / "pointer_gpf",
            ), patch(
                "v2.mcp_core.server.run_preflight",
                return_value=type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
            ), patch(
                "v2.mcp_core.server._ensure_play_mode",
                return_value={"status": "entered_play_mode"},
            ), patch(
                "v2.mcp_core.server.run_basic_flow",
                return_value={"status": "passed", "step_count": 5},
            ), patch(
                "v2.mcp_core.server._verify_teardown",
                return_value={"status": "failed", "project_process_count": 2},
            ), patch(
                "v2.mcp_core.server._list_project_processes",
                return_value=[],
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "TEARDOWN_VERIFICATION_FAILED")
        self.assertEqual(payload["error"]["details"]["project_close"]["project_process_count"], 2)


if __name__ == "__main__":
    unittest.main()
