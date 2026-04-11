import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.preflight import run_preflight


class PreflightTests(unittest.TestCase):
    def test_preflight_reports_missing_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_preflight(Path(tmp))
        self.assertFalse(result.ok)
        self.assertTrue(any(item.code == "PROJECT_FILE_MISSING" for item in result.issues))


if __name__ == "__main__":
    unittest.main()
