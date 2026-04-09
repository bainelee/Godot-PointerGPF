import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class McpGapAuditTests(unittest.TestCase):
    def test_gap_audit_generates_expected_sections(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        old_repo = r"D:/GODOT_Test/old-archives-sp"
        out_file = Path(tempfile.gettempdir()) / "mcp_gap_audit_out.json"
        if out_file.exists():
            out_file.unlink()
        proc = subprocess.run(
            [
                "python",
                str(repo_root / "scripts" / "mcp_gap_audit.py"),
                "--old-repo",
                old_repo,
                "--old-commit",
                "522744d",
                "--new-repo",
                str(repo_root),
                "--out",
                str(out_file),
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=f"{proc.stdout}\n{proc.stderr}")
        data = json.loads(out_file.read_text(encoding="utf-8"))
        self.assertIn("old_tool_surface", data)
        self.assertIn("new_tool_surface", data)
        self.assertIn("missing_tools", data)
        self.assertIn("missing_paths_by_prefix", data)
        self.assertIn("missing_path_samples", data)
        self.assertIsInstance(data["missing_path_samples"], dict)
