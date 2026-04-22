from __future__ import annotations

import unittest
from pathlib import Path

from v2.mcp_core.request_layer import (
    plan_user_request,
    resolve_basicflow_user_request,
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

    def test_user_request_command_guide_includes_both_domains(self) -> None:
        project_root = Path.cwd()

        result = user_request_command_guide(
            project_root,
            detect_basicflow_staleness=lambda _: {"status": "fresh", "is_stale": False, "reasons": []},
        )

        self.assertEqual(result["status"], "command_guide_ready")
        self.assertIn("basicflow", result["supported_domains"])
        self.assertIn("project_readiness", result["supported_domains"])


if __name__ == "__main__":
    unittest.main()
