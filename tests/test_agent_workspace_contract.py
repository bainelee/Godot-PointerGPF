"""仓库级 agent 契约：防止 Auto 模式下误删关键治理文件。"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class TestAgentWorkspaceContract(unittest.TestCase):
    def test_agents_md_has_binding_sections(self) -> None:
        path = REPO / "AGENTS.md"
        self.assertTrue(path.is_file(), "缺少仓库根目录 AGENTS.md")
        text = path.read_text(encoding="utf-8")
        for needle in (
            "## 指令优先级",
            "## 每轮强制自检（机械清单）",
            "## 禁止推卸责任",
            "## 与仓库规则的关系",
        ):
            self.assertIn(needle, text, f"AGENTS.md 缺少章节锚点: {needle}")

    def test_auto_mode_gates_rule_exists(self) -> None:
        path = REPO / ".cursor" / "rules" / "agent-auto-mode-gates.mdc"
        self.assertTrue(path.is_file(), "缺少 .cursor/rules/agent-auto-mode-gates.mdc")
        text = path.read_text(encoding="utf-8")
        self.assertIn("alwaysApply: true", text)
        for needle in (
            "先读取并遵循",
            "verification-before-completion",
            "blocking_point",
            "next_actions",
        ):
            self.assertIn(needle, text, f"规则文件缺少锚点: {needle}")
