"""CI：workflow 文本必须引用 legacy gameplayflow 关键工具名。"""

from __future__ import annotations

import unittest
from pathlib import Path


class CiLegacyCoverageTests(unittest.TestCase):
    def test_workflows_include_legacy_gameplayflow_commands(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        smoke = (repo / ".github" / "workflows" / "mcp-smoke.yml").read_text(encoding="utf-8")
        integ = (repo / ".github" / "workflows" / "mcp-integration.yml").read_text(encoding="utf-8")
        combined = smoke + integ
        self.assertIn("run_game_flow", combined)
        self.assertIn("start_stepwise_flow", combined)
        self.assertIn("pull_cursor_chat_plugin", combined)


if __name__ == "__main__":
    unittest.main()
