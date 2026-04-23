from __future__ import annotations

import unittest
from pathlib import Path

from v2.mcp_core.request_layer import (
    plan_user_request,
    resolve_basicflow_user_request,
    resolve_bug_repair_user_request,
    user_request_command_guide,
)


class RequestLayerTests(unittest.TestCase):
    def test_resolve_basicflow_user_request_routes_stale_run_to_generate(self) -> None:
        project_root = Path.cwd()
        result = resolve_basicflow_user_request(
            project_root,
            "run basicflow",
            detect_basicflow_staleness=lambda _: {"status": "stale", "is_stale": True, "reasons": []},
        )

        self.assertTrue(result["resolved"])
        self.assertEqual(result["tool"], "generate_basic_flow")
        self.assertEqual(result["matched_intent"]["tool"], "run_basic_flow")

    def test_plan_user_request_routes_configure_request_with_path(self) -> None:
        project_root = Path.cwd()
        exe_path = r"D:\Tools\Godot\Godot_v4.4.1-stable_win64.exe"

        result = plan_user_request(
            project_root,
            f"配置 godot 路径 {exe_path}",
            detect_basicflow_staleness=lambda _: {"status": "fresh", "is_stale": False, "reasons": []},
        )

        self.assertTrue(result["resolved"])
        self.assertEqual(result["domain"], "project_readiness")
        self.assertEqual(result["tool"], "configure_godot_executable")
        self.assertEqual(result["args"]["godot_executable"], exe_path)

    def test_resolve_bug_repair_user_request_extracts_expected_behavior(self) -> None:
        project_root = Path.cwd()

        result = resolve_bug_repair_user_request(
            project_root,
            "敌人在受击之后不会按照预期闪烁一次红色，帮我自动修复这个 bug",
        )

        self.assertTrue(result["resolved"])
        self.assertEqual(result["domain"], "bug_repair")
        self.assertEqual(result["tool"], "repair_reported_bug")
        self.assertTrue(result["ready_to_execute"])
        self.assertEqual(result["args"]["bug_report"], "敌人在受击之后不会按照预期闪烁一次红色")
        self.assertEqual(result["args"]["expected_behavior"], "敌人在受击之后应该闪烁一次红色")

    def test_plan_user_request_marks_bug_repair_request_missing_expected_behavior(self) -> None:
        project_root = Path.cwd()

        result = plan_user_request(
            project_root,
            "帮我修复这个 bug：敌人状态不对",
            detect_basicflow_staleness=lambda _: {"status": "fresh", "is_stale": False, "reasons": []},
        )

        self.assertTrue(result["resolved"])
        self.assertEqual(result["domain"], "bug_repair")
        self.assertEqual(result["tool"], "repair_reported_bug")
        self.assertFalse(result["ready_to_execute"])
        self.assertTrue(result["ask_confirmation"])
        self.assertIn("expected_behavior", result["plan"]["missing_fields"])

    def test_user_request_command_guide_includes_both_domains(self) -> None:
        project_root = Path.cwd()

        result = user_request_command_guide(
            project_root,
            detect_basicflow_staleness=lambda _: {"status": "fresh", "is_stale": False, "reasons": []},
        )

        self.assertEqual(result["status"], "command_guide_ready")
        self.assertIn("basicflow", result["supported_domains"])
        self.assertIn("project_readiness", result["supported_domains"])
        self.assertIn("bug_repair", result["supported_domains"])


if __name__ == "__main__":
    unittest.main()
