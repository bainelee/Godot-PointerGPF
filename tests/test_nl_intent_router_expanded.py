"""Expanded NL intent routing cases (Chinese phrasing)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

from nl_intent_router import route_nl_intent  # noqa: E402


class NlIntentRouterExpandedTests(unittest.TestCase):
    def test_common_phrasings_map_to_expected_tools(self) -> None:
        cases: list[tuple[str, str]] = [
            ("跑一下基础流程", "run_game_basic_test_flow_by_current_state"),
            ("帮我验证一下这个版本", "run_game_basic_test_flow_by_current_state"),
            ("做一个开局流程检查", "run_game_basic_test_flow_by_current_state"),
            ("检查大改后还能不能正常玩", "run_game_basic_test_flow_by_current_state"),
            ("设计一个基础测试流程", "design_game_basic_test_flow"),
            ("生成基础测试流程", "design_game_basic_test_flow"),
            ("帮我检查一下现在这版还能不能正常玩", "run_game_basic_test_flow_by_current_state"),
            ("创建一个基础测试流程", "design_game_basic_test_flow"),
            ("这个按钮点不了帮我自动修复", "auto_fix_game_bug"),
            ("按钮无法点击请自动修", "auto_fix_game_bug"),
            ("Figma 画面对照检查一下", "compare_figma_game_ui"),
            ("用设计稿和 UI 对比一下", "compare_figma_game_ui"),
            ("跑个冒烟看看游戏有没有问题", "run_game_basic_test_flow_by_current_state"),
            ("执行基础测试流程", "run_game_basic_test_flow_by_current_state"),
            ("开始游戏后跑一遍测试流程", "run_game_basic_test_flow_by_current_state"),
            ("跑一遍基础测试流程", "run_game_basic_test_flow_by_current_state"),
            ("要求跑基础测试流程", "run_game_basic_test_flow_by_current_state"),
            ("验证游戏流程是否正常", "run_game_basic_test_flow_by_current_state"),
            ("测一下当前版本主菜单流程", "run_game_basic_test_flow_by_current_state"),
            ("试一下 smoke 游戏流程", "run_game_basic_test_flow_by_current_state"),
            ("界面和 Figma 对比核查", "compare_figma_game_ui"),
            ("按钮按不了自动修复一下", "auto_fix_game_bug"),
        ]
        self.assertGreaterEqual(len(cases), 20, "plan requires at least 20 phrasings")
        for text, expected_tool in cases:
            with self.subTest(text=text):
                got = route_nl_intent(text).target_tool
                self.assertEqual(got, expected_tool, f"expected {expected_tool}, got {got}")

    def test_unknown_when_no_intent(self) -> None:
        self.assertEqual(route_nl_intent("今天天气真好").target_tool, "unknown")
        self.assertEqual(route_nl_intent("").target_tool, "unknown")


if __name__ == "__main__":
    unittest.main()
