import unittest
from pathlib import Path


class RestorationStatusDocumentTests(unittest.TestCase):
    def test_mcp_implementation_status_contains_legacy_restoration_keywords(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        path = repo_root / "docs" / "mcp-implementation-status.md"
        self.assertTrue(path.is_file(), msg=f"missing {path}")
        text = path.read_text(encoding="utf-8")
        for key in (
            "legacy_gameplayflow_tool_surface",
            "stepwise_chat_three_phase",
            "fix_loop_rounds_contract",
        ):
            self.assertIn(key, text, msg=f"expected keyword in {path}: {key!r}")


if __name__ == "__main__":
    unittest.main()
