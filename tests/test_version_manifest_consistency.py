import json
import subprocess
import sys
import unittest
from pathlib import Path


class VersionManifestConsistencyTests(unittest.TestCase):
    def test_cli_runtime_version_matches_manifest(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        manifest = json.loads((repo / "mcp" / "version_manifest.json").read_text(encoding="utf-8"))
        expected = str(manifest.get("current_version", "")).strip()
        self.assertTrue(expected)
        proc = subprocess.run(
            [sys.executable, str(repo / "mcp" / "server.py"), "--tool", "get_mcp_runtime_info", "--args", "{}"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload.get("ok"), payload)
        got = str(payload["result"]["server_version"])
        self.assertEqual(got, expected, f"CLI server_version {got!r} != manifest {expected!r}")

    def test_gtr_config_version_matches_manifest(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        manifest = json.loads((repo / "mcp" / "version_manifest.json").read_text(encoding="utf-8"))
        expected = str(manifest.get("current_version", "")).strip()
        gtr = json.loads((repo / "gtr.config.json").read_text(encoding="utf-8"))
        self.assertEqual(str(gtr.get("server_version", "")).strip(), expected)


if __name__ == "__main__":
    unittest.main()
