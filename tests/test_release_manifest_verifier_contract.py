"""轻量契约：release manifest 验收脚本存在且包含关键工具名字符串。"""

from __future__ import annotations

import unittest
from pathlib import Path


class ReleaseManifestVerifierContractTests(unittest.TestCase):
    def test_verifier_script_exists(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        script = repo / "scripts" / "verify-release-manifest-artifact.py"
        self.assertTrue(script.is_file(), f"missing {script}")

    def test_verifier_script_contains_required_tool_keywords(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        text = (repo / "scripts" / "verify-release-manifest-artifact.py").read_text(encoding="utf-8")
        for key in (
            "run_game_flow",
            "start_stepwise_flow",
            "pull_cursor_chat_plugin",
            "run_game_basic_test_flow",
            "check_test_runner_environment",
        ):
            with self.subTest(key=key):
                self.assertIn(key, text)


if __name__ == "__main__":
    unittest.main()
