import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from v2.mcp_core.server import _flow_lock_path, _normalize_execution_mode, main


class ServerCliTests(unittest.TestCase):
    def test_main_collect_bug_report_returns_normalized_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "collect_bug_report",
                        "project_root": str(project_root),
                        "bug_report": "点击开始游戏没有反应",
                        "bug_summary": None,
                        "expected_behavior": "应该进入游戏关卡",
                        "steps_to_trigger": "启动游戏|点击开始游戏",
                        "location_scene": "res://scenes/boot.tscn",
                        "location_node": "StartButton",
                        "location_script": "",
                        "frequency_hint": "always",
                        "severity_hint": "core_progression_blocker",
                    },
                )(),
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["schema"], "pointer_gpf.v2.bug_intake.v1")
        self.assertEqual(payload["result"]["expected_behavior"], "应该进入游戏关卡")

    def test_normalize_execution_mode_rejects_unknown_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported execution mode"):
            _normalize_execution_mode("desktop_magic")

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

    def test_main_get_basic_flow_user_intents_marks_missing_basicflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "get_basic_flow_user_intents",
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
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "missing", "is_stale": False, "reasons": [], "message": "missing"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "intents_ready")
        self.assertEqual(payload["result"]["basicflow_state"], "missing")
        self.assertEqual(payload["result"]["intents"][0]["availability"], "blocked_missing_basicflow")
        self.assertEqual(payload["result"]["intents"][1]["availability"], "recommended")
        self.assertEqual(payload["result"]["primary_recommendation"]["tool"], "generate_basic_flow")
        self.assertEqual(payload["result"]["secondary_actions"][0]["tool"], "get_basic_flow_generation_questions")

    def test_main_get_basic_flow_user_intents_marks_stale_basicflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "get_basic_flow_user_intents",
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
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "stale", "is_stale": True, "reasons": [], "message": "stale"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["basicflow_state"], "stale")
        self.assertEqual(payload["result"]["intents"][0]["availability"], "decision_required")
        self.assertEqual(payload["result"]["intents"][2]["availability"], "recommended")
        self.assertEqual(payload["result"]["primary_recommendation"]["tool"], "generate_basic_flow")
        self.assertEqual(payload["result"]["secondary_actions"][0]["tool"], "analyze_basic_flow_staleness")

    def test_main_get_basic_flow_user_intents_marks_fresh_basicflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "get_basic_flow_user_intents",
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
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["basicflow_state"], "fresh")
        self.assertEqual(payload["result"]["intents"][0]["availability"], "recommended")
        self.assertEqual(payload["result"]["intents"][1]["availability"], "available")
        self.assertEqual(payload["result"]["primary_recommendation"]["tool"], "run_basic_flow")

    def test_main_get_user_request_command_guide_returns_supported_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "get_user_request_command_guide",
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
                        "user_request": None,
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "command_guide_ready")
        self.assertIn("basicflow", payload["result"]["supported_domains"])
        self.assertIn("project_readiness", payload["result"]["supported_domains"])
        tools = {group["tool"] for group in payload["result"]["command_groups"]}
        self.assertIn("run_basic_flow", tools)
        self.assertIn("preflight_project", tools)
        self.assertIn("configure_godot_executable", tools)

    def test_main_resolve_basic_flow_user_request_routes_run_phrase_to_run_when_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "resolve_basic_flow_user_request",
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
                        "user_request": "跑基础测试流程",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "basicflow_request_resolved")
        self.assertTrue(payload["result"]["resolved"])
        self.assertEqual(payload["result"]["tool"], "run_basic_flow")
        self.assertFalse(payload["result"]["requires_confirmation"])
        self.assertEqual(payload["result"]["matched_intent"]["tool"], "run_basic_flow")
        self.assertEqual(payload["result"]["recommended_action"]["tool"], "run_basic_flow")

    def test_main_resolve_basic_flow_user_request_routes_run_phrase_to_generate_when_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "resolve_basic_flow_user_request",
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
                        "user_request": "run the basic test flow",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "stale", "is_stale": True, "reasons": [], "message": "stale"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["result"]["resolved"])
        self.assertEqual(payload["result"]["tool"], "generate_basic_flow")
        self.assertFalse(payload["result"]["requires_confirmation"])
        self.assertEqual(payload["result"]["matched_intent"]["tool"], "run_basic_flow")
        self.assertEqual(payload["result"]["recommended_action"]["tool"], "generate_basic_flow")

    def test_main_resolve_basic_flow_user_request_respects_explicit_analyze_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "resolve_basic_flow_user_request",
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
                        "user_request": "分析基础流程为什么过期",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "stale", "is_stale": True, "reasons": [], "message": "stale"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["result"]["resolved"])
        self.assertEqual(payload["result"]["tool"], "analyze_basic_flow_staleness")
        self.assertFalse(payload["result"]["requires_confirmation"])
        self.assertEqual(payload["result"]["matched_intent"]["tool"], "analyze_basic_flow_staleness")
        self.assertEqual(payload["result"]["recommended_action"]["tool"], "analyze_basic_flow_staleness")

    def test_main_resolve_basic_flow_user_request_returns_no_match_when_phrase_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "resolve_basic_flow_user_request",
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
                        "user_request": "帮我看看渲染性能",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "no_basicflow_intent_match")
        self.assertFalse(payload["result"]["resolved"])
        self.assertEqual(payload["result"]["tool"], "")

    def test_main_resolve_basic_flow_user_request_accepts_run_basicflow_synonym(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "resolve_basic_flow_user_request",
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
                        "user_request": "run basicflow",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["result"]["resolved"])
        self.assertEqual(payload["result"]["tool"], "run_basic_flow")

    def test_main_resolve_basic_flow_user_request_accepts_regenerate_synonym(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "resolve_basic_flow_user_request",
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
                        "user_request": "regenerate basicflow",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "stale", "is_stale": True, "reasons": [], "message": "stale"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["result"]["resolved"])
        self.assertEqual(payload["result"]["tool"], "generate_basic_flow")

    def test_main_resolve_basic_flow_user_request_accepts_inspect_drift_synonym(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "resolve_basic_flow_user_request",
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
                        "user_request": "inspect basicflow drift",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "stale", "is_stale": True, "reasons": [], "message": "stale"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["result"]["resolved"])
        self.assertEqual(payload["result"]["tool"], "analyze_basic_flow_staleness")

    def test_main_plan_basic_flow_user_request_routes_fresh_run_to_run_basic_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "plan_basic_flow_user_request",
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
                        "user_request": "run basicflow",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["tool"], "run_basic_flow")
        self.assertEqual(payload["result"]["args"]["project_root"], str(project_root.resolve()))
        self.assertTrue(payload["result"]["ready_to_execute"])
        self.assertFalse(payload["result"]["ask_confirmation"])

    def test_main_plan_basic_flow_user_request_routes_stale_run_to_generation_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "plan_basic_flow_user_request",
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
                        "user_request": "跑基础测试流程",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "stale", "is_stale": True, "reasons": [], "message": "stale"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["tool"], "get_basic_flow_generation_questions")
        self.assertEqual(payload["result"]["follow_up_tool"], "generate_basic_flow")
        self.assertTrue(payload["result"]["ready_to_execute"])
        self.assertFalse(payload["result"]["ask_confirmation"])

    def test_main_plan_basic_flow_user_request_routes_explicit_generate_to_generation_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "plan_basic_flow_user_request",
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
                        "user_request": "regenerate basicflow",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "stale", "is_stale": True, "reasons": [], "message": "stale"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["tool"], "get_basic_flow_generation_questions")
        self.assertEqual(payload["result"]["follow_up_tool"], "generate_basic_flow")

    def test_main_plan_basic_flow_user_request_routes_explicit_analyze_to_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "plan_basic_flow_user_request",
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
                        "user_request": "inspect basicflow drift",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "stale", "is_stale": True, "reasons": [], "message": "stale"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["tool"], "analyze_basic_flow_staleness")
        self.assertEqual(payload["result"]["args"]["project_root"], str(project_root.resolve()))

    def test_main_plan_user_request_routes_basicflow_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "plan_user_request",
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
                        "user_request": "run basicflow",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "user_request_planned")
        self.assertEqual(payload["result"]["domain"], "basicflow")
        self.assertEqual(payload["result"]["tool"], "run_basic_flow")

    def test_main_plan_user_request_returns_no_plan_for_unknown_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "plan_user_request",
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
                        "user_request": "帮我看看渲染性能",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "no_user_request_plan")
        self.assertFalse(payload["result"]["resolved"])

    def test_main_plan_user_request_routes_preflight_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "plan_user_request",
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
                        "user_request": "跑项目预检",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["domain"], "project_readiness")
        self.assertEqual(payload["result"]["tool"], "preflight_project")
        self.assertTrue(payload["result"]["ready_to_execute"])

    def test_main_plan_user_request_routes_configure_godot_without_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "plan_user_request",
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
                        "user_request": "配置 godot 路径",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["domain"], "project_readiness")
        self.assertEqual(payload["result"]["tool"], "configure_godot_executable")
        self.assertFalse(payload["result"]["ready_to_execute"])
        self.assertTrue(payload["result"]["ask_confirmation"])

    def test_main_plan_user_request_routes_configure_godot_with_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            exe_path = r"D:\Tools\Godot\Godot_v4.4.1-stable_win64.exe"
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "plan_user_request",
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
                        "user_request": f"配置 godot 路径 {exe_path}",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["tool"], "configure_godot_executable")
        self.assertEqual(payload["result"]["args"]["godot_executable"], exe_path)
        self.assertTrue(payload["result"]["ready_to_execute"])

    def test_main_handle_user_request_executes_preflight_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            preflight_result = type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True, "status": "ready"}})()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "handle_user_request",
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
                        "user_request": "跑项目预检",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), patch("v2.mcp_core.server.run_preflight", return_value=preflight_result), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "user_request_handled")
        self.assertEqual(payload["result"]["tool"], "preflight_project")
        self.assertEqual(payload["result"]["result"]["status"], "ready")

    def test_main_handle_user_request_returns_needs_input_for_configure_without_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "handle_user_request",
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
                        "user_request": "配置 godot 路径",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "user_request_needs_input")
        self.assertEqual(payload["result"]["tool"], "configure_godot_executable")
        self.assertTrue(payload["result"]["ask_confirmation"])

    def test_main_handle_user_request_executes_configure_with_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            exe_path = r"D:\Tools\Godot\Godot_v4.4.1-stable_win64.exe"
            config_file = project_root / "pointer_gpf" / "godot_executable.json"
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "handle_user_request",
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
                        "user_request": f"配置 godot 路径 {exe_path}",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "fresh", "is_stale": False, "reasons": [], "message": "fresh"},
            ), patch("v2.mcp_core.server.configure_godot_executable", return_value=config_file), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "user_request_handled")
        self.assertEqual(payload["result"]["tool"], "configure_godot_executable")
        self.assertEqual(payload["result"]["result"]["config_file"], str(config_file))

    def test_main_handle_user_request_executes_generation_question_collection_for_stale_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "handle_user_request",
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
                        "user_request": "run basicflow",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "stale", "is_stale": True, "reasons": [], "message": "stale"},
            ), patch(
                "v2.mcp_core.server.get_basicflow_generation_questions",
                return_value={"status": "questions_ready", "questions": [{"id": "main_scene_is_entry"}]},
            ), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "user_request_handled")
        self.assertEqual(payload["result"]["tool"], "get_basic_flow_generation_questions")
        self.assertEqual(payload["result"]["follow_up_tool"], "generate_basic_flow")

    def test_main_handle_user_request_executes_basicflow_staleness_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            stdout = StringIO()
            analysis = {"status": "stale", "is_stale": True, "reasons": ["startup script changed"]}
            with patch(
                "v2.mcp_core.server._parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "tool": "handle_user_request",
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
                        "user_request": "inspect basicflow drift",
                    },
                )(),
            ), patch(
                "v2.mcp_core.server.detect_basicflow_staleness",
                return_value={"status": "stale", "is_stale": True, "reasons": [], "message": "stale"},
            ), patch("v2.mcp_core.server.analyze_basicflow_staleness", return_value=analysis), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "user_request_handled")
        self.assertEqual(payload["result"]["tool"], "analyze_basic_flow_staleness")
        self.assertEqual(payload["result"]["result"]["reasons"][0], "startup script changed")

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
