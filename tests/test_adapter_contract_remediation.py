"""Adapter contract includes remediation_matrix."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class TestAdapterContractRemediation(unittest.TestCase):
    def test_remediation_matrix_version(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        path = repo / "mcp" / "adapter_contract_v1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        matrix = data.get("remediation_matrix")
        self.assertIsInstance(matrix, dict)
        self.assertEqual(matrix.get("version"), 1)
        rows = matrix.get("rows")
        self.assertIsInstance(rows, list)
        self.assertGreaterEqual(len(rows), 6)
        classes = {r.get("remediation_class") for r in rows if isinstance(r, dict)}
        self.assertIn("runtime_gate", classes)
        self.assertIn("flow_generation_blocked", classes)


if __name__ == "__main__":
    unittest.main()
