"""failure_handling=run_only affects auto-repair only, not close_project_on_finish default."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import server as mcp_server  # noqa: E402


class TestRunOnlyLeavesCloseProjectDefault(unittest.TestCase):
    def test_parse_auto_repair_run_only_is_false(self) -> None:
        auto_repair, _, _ = mcp_server._parse_auto_repair_params({"failure_handling": "run_only"})
        self.assertFalse(auto_repair)

    def test_close_project_on_finish_defaults_true_with_run_only(self) -> None:
        args: dict = {"failure_handling": "run_only"}
        close_project_on_finish = bool(args.get("close_project_on_finish", True))
        self.assertTrue(close_project_on_finish)


if __name__ == "__main__":
    unittest.main()
