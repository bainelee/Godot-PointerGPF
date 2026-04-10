"""Tests for L2 repair hook (repair_backend) and bug_fix_loop integration."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import bug_fix_loop  # noqa: E402
from repair_backend import build_l2_try_patch_from_env  # noqa: E402


class TestRepairBackendEnv(unittest.TestCase):
    @mock.patch.dict(os.environ, {"GPF_REPAIR_BACKEND_CMD": ""}, clear=False)
    def test_build_l2_none_when_cmd_empty(self) -> None:
        self.assertIsNone(build_l2_try_patch_from_env())


class TestBugFixLoopL2(unittest.TestCase):
    @mock.patch("bug_fix_loop.run_apply_patch")
    @mock.patch("bug_fix_loop.run_diagnosis")
    def test_l2_applied_when_l1_not(self, mock_diag: mock.MagicMock, mock_patch: mock.MagicMock) -> None:
        mock_diag.return_value = {"strategy_id": "generic", "summary": "x"}
        mock_patch.return_value = {"applied": False, "notes": "l1 noop"}

        def l2(
            root: Path,
            issue: str,
            diagnosis: dict,
            verification: dict,
        ) -> dict:
            _ = (root, issue, diagnosis, verification)
            return {"applied": True, "changed_files": [], "notes": "l2"}

        n = {"c": 0}

        def verify() -> dict:
            n["c"] += 1
            return {"passed": n["c"] >= 2, "status": "passed" if n["c"] >= 2 else "failed"}

        out = bug_fix_loop.run_bug_fix_loop(
            project_root=Path("."),
            issue="btn",
            max_cycles=1,
            timeout_seconds=None,
            run_verification=verify,
            l2_try_patch=l2,
        )
        self.assertEqual(out["final_status"], "fixed")


if __name__ == "__main__":
    unittest.main()
