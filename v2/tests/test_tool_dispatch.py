from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.tool_dispatch import ToolDispatchApi, dispatch_tool


class ToolDispatchTests(unittest.TestCase):
    def test_dispatch_collect_bug_report_returns_normalized_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = type(
                "Args",
                (),
                {
                    "tool": "collect_bug_report",
                    "bug_report": "点击开始游戏没有反应",
                    "bug_summary": None,
                    "expected_behavior": "应该进入关卡",
                    "steps_to_trigger": "启动游戏|点击开始游戏",
                    "location_scene": "res://scenes/boot.tscn",
                    "location_node": "StartButton",
                    "location_script": "",
                    "frequency_hint": "always",
                    "severity_hint": "core_progression_blocker",
                },
            )()
            api = ToolDispatchApi(
                collect_bug_report=lambda project_root_arg, args_arg: {
                    "schema": "pointer_gpf.v2.bug_intake.v1",
                    "project_root": str(project_root_arg),
                    "observed_behavior": args_arg.bug_report,
                    "expected_behavior": args_arg.expected_behavior,
                },
                analyze_bug_report=lambda *_: {},
                define_bug_assertions=lambda *_: {},
                plan_bug_repro_flow=lambda *_: {},
                run_bug_repro_flow=lambda *_: {},
                plan_bug_fix=lambda *_: {},
                apply_bug_fix=lambda *_: {},
                configure_godot_executable=lambda *_: project_root / "cfg.json",
                sync_project_plugin=lambda *_: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda *_: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                resolve_requested_flow_file=lambda *_: (None, None, None),
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
                collect_inline_generation_answers=lambda *_: None,
                generate_basicflow_from_answers_file=lambda *_: {},
                generate_basicflow_from_answers=lambda *_: {},
                get_basicflow_generation_questions=lambda *_: {},
                get_basicflow_user_intents=lambda *_: {},
                get_user_request_command_guide=lambda *_: {},
                resolve_basicflow_user_request=lambda *_: {},
                plan_basicflow_user_request=lambda *_: {},
                plan_user_request=lambda *_: {},
                handle_user_request=lambda *_: {},
                start_basicflow_generation_session=lambda *_: {},
                answer_basicflow_generation_session=lambda *_: {},
                complete_basicflow_generation_session=lambda *_: {},
                analyze_basicflow_staleness=lambda *_: {},
            )

            exit_code, payload = dispatch_tool(args, project_root, api)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["schema"], "pointer_gpf.v2.bug_intake.v1")

    def test_dispatch_collect_bug_report_returns_incomplete_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = type("Args", (), {"tool": "collect_bug_report"})()
            api = ToolDispatchApi(
                collect_bug_report=lambda *_: (_ for _ in ()).throw(
                    ValueError("collect_bug_report requires bug_report and expected_behavior, plus at least one summary/steps/location hint")
                ),
                analyze_bug_report=lambda *_: {},
                define_bug_assertions=lambda *_: {},
                plan_bug_repro_flow=lambda *_: {},
                run_bug_repro_flow=lambda *_: {},
                plan_bug_fix=lambda *_: {},
                apply_bug_fix=lambda *_: {},
                configure_godot_executable=lambda *_: project_root / "cfg.json",
                sync_project_plugin=lambda *_: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda *_: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                resolve_requested_flow_file=lambda *_: (None, None, None),
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
                collect_inline_generation_answers=lambda *_: None,
                generate_basicflow_from_answers_file=lambda *_: {},
                generate_basicflow_from_answers=lambda *_: {},
                get_basicflow_generation_questions=lambda *_: {},
                get_basicflow_user_intents=lambda *_: {},
                get_user_request_command_guide=lambda *_: {},
                resolve_basicflow_user_request=lambda *_: {},
                plan_basicflow_user_request=lambda *_: {},
                plan_user_request=lambda *_: {},
                handle_user_request=lambda *_: {},
                start_basicflow_generation_session=lambda *_: {},
                answer_basicflow_generation_session=lambda *_: {},
                complete_basicflow_generation_session=lambda *_: {},
                analyze_basicflow_staleness=lambda *_: {},
            )

            exit_code, payload = dispatch_tool(args, project_root, api)

        self.assertEqual(exit_code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "BUG_REPORT_INCOMPLETE")

    def test_dispatch_analyze_bug_report_returns_analysis_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = type(
                "Args",
                (),
                {
                    "tool": "analyze_bug_report",
                    "bug_report": "点击开始游戏没有反应",
                    "bug_summary": None,
                    "expected_behavior": "应该进入关卡",
                    "steps_to_trigger": "启动游戏|点击开始游戏",
                    "location_scene": "res://scenes/boot.tscn",
                    "location_node": "StartButton",
                    "location_script": "",
                    "frequency_hint": "always",
                    "severity_hint": "core_progression_blocker",
                },
            )()
            api = ToolDispatchApi(
                collect_bug_report=lambda *_: {},
                analyze_bug_report=lambda project_root_arg, args_arg: {
                    "schema": "pointer_gpf.v2.bug_analysis.v1",
                    "project_root": str(project_root_arg),
                    "bug_summary": args_arg.bug_report,
                },
                define_bug_assertions=lambda *_: {},
                plan_bug_repro_flow=lambda *_: {},
                run_bug_repro_flow=lambda *_: {},
                plan_bug_fix=lambda *_: {},
                apply_bug_fix=lambda *_: {},
                configure_godot_executable=lambda *_: project_root / "cfg.json",
                sync_project_plugin=lambda *_: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda *_: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                resolve_requested_flow_file=lambda *_: (None, None, None),
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
                collect_inline_generation_answers=lambda *_: None,
                generate_basicflow_from_answers_file=lambda *_: {},
                generate_basicflow_from_answers=lambda *_: {},
                get_basicflow_generation_questions=lambda *_: {},
                get_basicflow_user_intents=lambda *_: {},
                get_user_request_command_guide=lambda *_: {},
                resolve_basicflow_user_request=lambda *_: {},
                plan_basicflow_user_request=lambda *_: {},
                plan_user_request=lambda *_: {},
                handle_user_request=lambda *_: {},
                start_basicflow_generation_session=lambda *_: {},
                answer_basicflow_generation_session=lambda *_: {},
                complete_basicflow_generation_session=lambda *_: {},
                analyze_basicflow_staleness=lambda *_: {},
            )

            exit_code, payload = dispatch_tool(args, project_root, api)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["schema"], "pointer_gpf.v2.bug_analysis.v1")

    def test_dispatch_define_bug_assertions_returns_assertion_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = type(
                "Args",
                (),
                {
                    "tool": "define_bug_assertions",
                    "bug_report": "点击开始游戏没有反应",
                    "bug_summary": None,
                    "expected_behavior": "应该进入关卡",
                    "steps_to_trigger": "启动游戏|点击开始游戏",
                    "location_scene": "res://scenes/boot.tscn",
                    "location_node": "StartButton",
                    "location_script": "",
                    "frequency_hint": "always",
                    "severity_hint": "core_progression_blocker",
                },
            )()
            api = ToolDispatchApi(
                collect_bug_report=lambda *_: {},
                analyze_bug_report=lambda *_: {},
                define_bug_assertions=lambda project_root_arg, args_arg: {
                    "schema": "pointer_gpf.v2.assertion_set.v1",
                    "project_root": str(project_root_arg),
                    "bug_summary": args_arg.bug_report,
                    "assertions": [],
                },
                plan_bug_repro_flow=lambda *_: {},
                run_bug_repro_flow=lambda *_: {},
                plan_bug_fix=lambda *_: {},
                apply_bug_fix=lambda *_: {},
                configure_godot_executable=lambda *_: project_root / "cfg.json",
                sync_project_plugin=lambda *_: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda *_: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                resolve_requested_flow_file=lambda *_: (None, None, None),
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
                collect_inline_generation_answers=lambda *_: None,
                generate_basicflow_from_answers_file=lambda *_: {},
                generate_basicflow_from_answers=lambda *_: {},
                get_basicflow_generation_questions=lambda *_: {},
                get_basicflow_user_intents=lambda *_: {},
                get_user_request_command_guide=lambda *_: {},
                resolve_basicflow_user_request=lambda *_: {},
                plan_basicflow_user_request=lambda *_: {},
                plan_user_request=lambda *_: {},
                handle_user_request=lambda *_: {},
                start_basicflow_generation_session=lambda *_: {},
                answer_basicflow_generation_session=lambda *_: {},
                complete_basicflow_generation_session=lambda *_: {},
                analyze_basicflow_staleness=lambda *_: {},
            )

            exit_code, payload = dispatch_tool(args, project_root, api)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["schema"], "pointer_gpf.v2.assertion_set.v1")

    def test_dispatch_plan_bug_repro_flow_returns_plan_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = type(
                "Args",
                (),
                {
                    "tool": "plan_bug_repro_flow",
                    "bug_report": "点击开始游戏没有反应",
                    "bug_summary": None,
                    "expected_behavior": "应该进入关卡",
                    "steps_to_trigger": "启动游戏|点击开始游戏",
                    "location_scene": "res://scenes/boot.tscn",
                    "location_node": "StartButton",
                    "location_script": "",
                    "frequency_hint": "always",
                    "severity_hint": "core_progression_blocker",
                },
            )()
            api = ToolDispatchApi(
                collect_bug_report=lambda *_: {},
                analyze_bug_report=lambda *_: {},
                define_bug_assertions=lambda *_: {},
                plan_bug_repro_flow=lambda project_root_arg, args_arg: {
                    "schema": "pointer_gpf.v2.repro_flow_plan.v1",
                    "project_root": str(project_root_arg),
                    "bug_summary": args_arg.bug_report,
                    "candidate_flow": {"steps": []},
                },
                run_bug_repro_flow=lambda *_: {},
                plan_bug_fix=lambda *_: {},
                apply_bug_fix=lambda *_: {},
                configure_godot_executable=lambda *_: project_root / "cfg.json",
                sync_project_plugin=lambda *_: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda *_: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                resolve_requested_flow_file=lambda *_: (None, None, None),
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
                collect_inline_generation_answers=lambda *_: None,
                generate_basicflow_from_answers_file=lambda *_: {},
                generate_basicflow_from_answers=lambda *_: {},
                get_basicflow_generation_questions=lambda *_: {},
                get_basicflow_user_intents=lambda *_: {},
                get_user_request_command_guide=lambda *_: {},
                resolve_basicflow_user_request=lambda *_: {},
                plan_basicflow_user_request=lambda *_: {},
                plan_user_request=lambda *_: {},
                handle_user_request=lambda *_: {},
                start_basicflow_generation_session=lambda *_: {},
                answer_basicflow_generation_session=lambda *_: {},
                complete_basicflow_generation_session=lambda *_: {},
                analyze_basicflow_staleness=lambda *_: {},
            )

            exit_code, payload = dispatch_tool(args, project_root, api)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["schema"], "pointer_gpf.v2.repro_flow_plan.v1")

    def test_dispatch_run_bug_repro_flow_returns_run_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = type(
                "Args",
                (),
                {
                    "tool": "run_bug_repro_flow",
                    "execution_mode": "play_mode",
                    "bug_report": "点击开始游戏没有反应",
                    "bug_summary": None,
                    "expected_behavior": "应该进入关卡",
                    "steps_to_trigger": "启动游戏|点击开始游戏",
                    "location_scene": "res://scenes/boot.tscn",
                    "location_node": "StartButton",
                    "location_script": "",
                    "frequency_hint": "always",
                    "severity_hint": "core_progression_blocker",
                },
            )()
            api = ToolDispatchApi(
                collect_bug_report=lambda *_: {},
                analyze_bug_report=lambda *_: {},
                define_bug_assertions=lambda *_: {},
                plan_bug_repro_flow=lambda *_: {},
                run_bug_repro_flow=lambda project_root_arg, args_arg, execution_mode: {
                    "schema": "pointer_gpf.v2.repro_run.v1",
                    "project_root": str(project_root_arg),
                    "status": "bug_not_reproduced",
                    "execution_mode": execution_mode,
                },
                plan_bug_fix=lambda *_: {},
                apply_bug_fix=lambda *_: {},
                configure_godot_executable=lambda *_: project_root / "cfg.json",
                sync_project_plugin=lambda *_: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda *_: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                resolve_requested_flow_file=lambda *_: (None, None, None),
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
                collect_inline_generation_answers=lambda *_: None,
                generate_basicflow_from_answers_file=lambda *_: {},
                generate_basicflow_from_answers=lambda *_: {},
                get_basicflow_generation_questions=lambda *_: {},
                get_basicflow_user_intents=lambda *_: {},
                get_user_request_command_guide=lambda *_: {},
                resolve_basicflow_user_request=lambda *_: {},
                plan_basicflow_user_request=lambda *_: {},
                plan_user_request=lambda *_: {},
                handle_user_request=lambda *_: {},
                start_basicflow_generation_session=lambda *_: {},
                answer_basicflow_generation_session=lambda *_: {},
                complete_basicflow_generation_session=lambda *_: {},
                analyze_basicflow_staleness=lambda *_: {},
            )

            exit_code, payload = dispatch_tool(args, project_root, api)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["schema"], "pointer_gpf.v2.repro_run.v1")

    def test_dispatch_plan_bug_fix_returns_fix_plan_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = type(
                "Args",
                (),
                {
                    "tool": "plan_bug_fix",
                    "execution_mode": "play_mode",
                    "bug_report": "点击开始游戏没有反应",
                    "bug_summary": None,
                    "expected_behavior": "应该进入关卡",
                    "steps_to_trigger": "启动游戏|点击开始游戏",
                    "location_scene": "res://scenes/boot.tscn",
                    "location_node": "StartButton",
                    "location_script": "",
                    "frequency_hint": "always",
                    "severity_hint": "core_progression_blocker",
                },
            )()
            api = ToolDispatchApi(
                collect_bug_report=lambda *_: {},
                analyze_bug_report=lambda *_: {},
                define_bug_assertions=lambda *_: {},
                plan_bug_repro_flow=lambda *_: {},
                run_bug_repro_flow=lambda *_: {},
                plan_bug_fix=lambda project_root_arg, args_arg: {
                    "schema": "pointer_gpf.v2.fix_plan.v1",
                    "project_root": str(project_root_arg),
                    "bug_summary": args_arg.bug_report,
                    "status": "fix_not_ready",
                },
                apply_bug_fix=lambda *_: {},
                configure_godot_executable=lambda *_: project_root / "cfg.json",
                sync_project_plugin=lambda *_: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda *_: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                resolve_requested_flow_file=lambda *_: (None, None, None),
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
                collect_inline_generation_answers=lambda *_: None,
                generate_basicflow_from_answers_file=lambda *_: {},
                generate_basicflow_from_answers=lambda *_: {},
                get_basicflow_generation_questions=lambda *_: {},
                get_basicflow_user_intents=lambda *_: {},
                get_user_request_command_guide=lambda *_: {},
                resolve_basicflow_user_request=lambda *_: {},
                plan_basicflow_user_request=lambda *_: {},
                plan_user_request=lambda *_: {},
                handle_user_request=lambda *_: {},
                start_basicflow_generation_session=lambda *_: {},
                answer_basicflow_generation_session=lambda *_: {},
                complete_basicflow_generation_session=lambda *_: {},
                analyze_basicflow_staleness=lambda *_: {},
            )

            exit_code, payload = dispatch_tool(args, project_root, api)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["schema"], "pointer_gpf.v2.fix_plan.v1")

    def test_dispatch_apply_bug_fix_returns_apply_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = type(
                "Args",
                (),
                {
                    "tool": "apply_bug_fix",
                    "execution_mode": "play_mode",
                    "bug_report": "点击开始游戏没有反应",
                    "bug_summary": None,
                    "expected_behavior": "应该进入关卡",
                    "steps_to_trigger": "启动游戏|点击开始游戏",
                    "location_scene": "res://scenes/boot.tscn",
                    "location_node": "StartButton",
                    "location_script": "",
                    "frequency_hint": "always",
                    "severity_hint": "core_progression_blocker",
                },
            )()
            api = ToolDispatchApi(
                collect_bug_report=lambda *_: {},
                analyze_bug_report=lambda *_: {},
                define_bug_assertions=lambda *_: {},
                plan_bug_repro_flow=lambda *_: {},
                run_bug_repro_flow=lambda *_: {},
                plan_bug_fix=lambda *_: {},
                apply_bug_fix=lambda project_root_arg, args_arg: {
                    "schema": "pointer_gpf.v2.fix_apply.v1",
                    "project_root": str(project_root_arg),
                    "bug_summary": args_arg.bug_report,
                    "status": "fix_not_applied",
                },
                configure_godot_executable=lambda *_: project_root / "cfg.json",
                sync_project_plugin=lambda *_: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda *_: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                resolve_requested_flow_file=lambda *_: (None, None, None),
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
                collect_inline_generation_answers=lambda *_: None,
                generate_basicflow_from_answers_file=lambda *_: {},
                generate_basicflow_from_answers=lambda *_: {},
                get_basicflow_generation_questions=lambda *_: {},
                get_basicflow_user_intents=lambda *_: {},
                get_user_request_command_guide=lambda *_: {},
                resolve_basicflow_user_request=lambda *_: {},
                plan_basicflow_user_request=lambda *_: {},
                plan_user_request=lambda *_: {},
                handle_user_request=lambda *_: {},
                start_basicflow_generation_session=lambda *_: {},
                answer_basicflow_generation_session=lambda *_: {},
                complete_basicflow_generation_session=lambda *_: {},
                analyze_basicflow_staleness=lambda *_: {},
            )

            exit_code, payload = dispatch_tool(args, project_root, api)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["schema"], "pointer_gpf.v2.fix_apply.v1")

    def test_dispatch_handle_user_request_uses_nested_result_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = type("Args", (), {"tool": "handle_user_request", "user_request": "跑项目预检"})()
            api = ToolDispatchApi(
                collect_bug_report=lambda *_: {},
                analyze_bug_report=lambda *_: {},
                define_bug_assertions=lambda *_: {},
                plan_bug_repro_flow=lambda *_: {},
                run_bug_repro_flow=lambda *_: {},
                plan_bug_fix=lambda *_: {},
                apply_bug_fix=lambda *_: {},
                configure_godot_executable=lambda *_: project_root / "cfg.json",
                sync_project_plugin=lambda *_: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda *_: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                resolve_requested_flow_file=lambda *_: (None, None, None),
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
                collect_inline_generation_answers=lambda *_: None,
                generate_basicflow_from_answers_file=lambda *_: {},
                generate_basicflow_from_answers=lambda *_: {},
                get_basicflow_generation_questions=lambda *_: {},
                get_basicflow_user_intents=lambda *_: {},
                get_user_request_command_guide=lambda *_: {},
                resolve_basicflow_user_request=lambda *_: {},
                plan_basicflow_user_request=lambda *_: {},
                plan_user_request=lambda *_: {},
                handle_user_request=lambda *_: {"status": "user_request_handled", "result": {"ok": True, "status": "ready"}},
                start_basicflow_generation_session=lambda *_: {},
                answer_basicflow_generation_session=lambda *_: {},
                complete_basicflow_generation_session=lambda *_: {},
                analyze_basicflow_staleness=lambda *_: {},
            )

            exit_code, payload = dispatch_tool(args, project_root, api)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "user_request_handled")

    def test_dispatch_generate_basic_flow_requires_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = type("Args", (), {"tool": "generate_basic_flow", "answers_file": None})()
            api = ToolDispatchApi(
                collect_bug_report=lambda *_: {},
                analyze_bug_report=lambda *_: {},
                define_bug_assertions=lambda *_: {},
                plan_bug_repro_flow=lambda *_: {},
                run_bug_repro_flow=lambda *_: {},
                plan_bug_fix=lambda *_: {},
                apply_bug_fix=lambda *_: {},
                configure_godot_executable=lambda *_: project_root / "cfg.json",
                sync_project_plugin=lambda *_: project_root / "addons" / "pointer_gpf",
                run_preflight=lambda *_: type("PreflightResult", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
                resolve_requested_flow_file=lambda *_: (None, None, None),
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
                collect_inline_generation_answers=lambda *_: None,
                generate_basicflow_from_answers_file=lambda *_: {},
                generate_basicflow_from_answers=lambda *_: {},
                get_basicflow_generation_questions=lambda *_: {},
                get_basicflow_user_intents=lambda *_: {},
                get_user_request_command_guide=lambda *_: {},
                resolve_basicflow_user_request=lambda *_: {},
                plan_basicflow_user_request=lambda *_: {},
                plan_user_request=lambda *_: {},
                handle_user_request=lambda *_: {},
                start_basicflow_generation_session=lambda *_: {},
                answer_basicflow_generation_session=lambda *_: {},
                complete_basicflow_generation_session=lambda *_: {},
                analyze_basicflow_staleness=lambda *_: {},
            )

            exit_code, payload = dispatch_tool(args, project_root, api)

        self.assertEqual(exit_code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "BASICFLOW_GENERATION_ANSWERS_REQUIRED")


if __name__ == "__main__":
    unittest.main()
