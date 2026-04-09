"""发布包单目录载荷（pointer_gpf）契约：workflow 与 manifest 文本约束。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class ReleaseSingleDirectoryLayoutTests(unittest.TestCase):
    def test_manifest_zip_layout_is_pointer_gpf_root(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        payload = json.loads((repo / "mcp" / "version_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            payload["channels"]["stable"]["artifact"]["zip_layout"],
            "pointer_gpf_root",
        )

    def test_release_workflow_packages_pointer_gpf_root(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        wf = (repo / ".github" / "workflows" / "release-package.yml").read_text(encoding="utf-8")
        self.assertIn('Join-Path $stageDir "pointer_gpf"', wf)
        self.assertIn('Copy-Item -LiteralPath "tools/game-test-runner"', wf)
        self.assertIn('Copy-Item -LiteralPath "flows"', wf)

    def test_root_entry_points_to_nested_install_script(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        cmd = (repo / "pointer-gpf.cmd").read_text(encoding="utf-8")
        self.assertIn("pointer_gpf\\install\\pointer-gpf.ps1", cmd)

    def test_update_script_supports_pointer_gpf_payload_and_legacy_assets(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        script = (repo / "install" / "update-mcp.ps1").read_text(encoding="utf-8")
        self.assertIn('Join-Path $BaseDir "pointer_gpf"', script)
        self.assertIn('$normalized.StartsWith("pointer_gpf/")', script)
        self.assertIn('name = "tools/game-test-runner"', script)
        self.assertIn('name = "flows"', script)

    def test_release_workflow_runs_package_layout_verifier(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        wf = (repo / ".github" / "workflows" / "release-package.yml").read_text(encoding="utf-8")
        self.assertIn("verify-release-package-layout.py", wf)


if __name__ == "__main__":
    unittest.main()
