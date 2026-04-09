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

    def test_release_workflow_supports_tag_trigger_and_ref_version_parse(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        wf = (repo / ".github" / "workflows" / "release-package.yml").read_text(encoding="utf-8")
        self.assertIn("push:", wf)
        self.assertIn("tags:", wf)
        self.assertIn('"v*"', wf)
        self.assertIn("github.ref_name", wf)

    def test_mcp_smoke_workflow_has_concurrency_and_paths_ignore(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        wf = (repo / ".github" / "workflows" / "mcp-smoke.yml").read_text(encoding="utf-8")
        self.assertIn("concurrency:", wf)
        self.assertIn("cancel-in-progress: true", wf)
        self.assertIn("paths-ignore:", wf)
        self.assertIn("**/*.md", wf)

    def test_mcp_integration_workflow_dispatch_has_scope_input(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        wf = (repo / ".github" / "workflows" / "mcp-integration.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", wf)
        self.assertIn("inputs:", wf)
        self.assertIn("scope:", wf)
        self.assertIn("quick|full", wf)

    def test_docs_mention_one_command_release_entry(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        quickstart = (repo / "docs" / "quickstart.md").read_text(encoding="utf-8")
        readme = (repo / "README.md").read_text(encoding="utf-8")
        readme_zh = (repo / "README.zh-CN.md").read_text(encoding="utf-8")
        changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("scripts/release.ps1", quickstart)
        self.assertIn("scripts/release.ps1", readme)
        self.assertIn("scripts/release.ps1", readme_zh)
        self.assertIn("VERSION", readme)
        self.assertIn("VERSION", readme_zh)
        self.assertIn("scripts/release.ps1", changelog)


if __name__ == "__main__":
    unittest.main()
