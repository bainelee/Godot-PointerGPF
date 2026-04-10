"""Tests for RemediationTrace structure."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import remediation_trace as rt  # noqa: E402


class TestRemediationTrace(unittest.TestCase):
    def test_append_emits_ordered_phases(self) -> None:
        tr = rt.RemediationTrace(run_id="r1")
        tr.append("verify", {"passed": False})
        tr.append("locate", {"strategy_id": "generic"})
        tr.append("patch", {"applied": False})
        tr.append("retest", {"passed": True})
        data = tr.to_json()
        kinds = [e["kind"] for e in data["events"]]
        self.assertEqual(kinds, ["verify", "locate", "patch", "retest"])


if __name__ == "__main__":
    unittest.main()
