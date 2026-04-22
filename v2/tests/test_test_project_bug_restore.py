import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.test_project_bug_restore import restore_test_project_bug_round
from v2.mcp_core.test_project_bug_round import record_bug_round_baseline


class TestProjectBugRestoreTests(unittest.TestCase):
    def test_restore_test_project_bug_round_restores_files_and_runs_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "main_menu_flow.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("original\n", encoding="utf-8")
            record_bug_round_baseline(project_root, "round-005", ["scripts/main_menu_flow.gd"])
            script_path.write_text("mutated\n", encoding="utf-8")
            args = type("Args", (), {"round_id": "round-005"})()

            payload = restore_test_project_bug_round(
                project_root,
                args,
                build_command=lambda _: ["python", "fake_verify.py"],
                subprocess_run=lambda *_, **__: subprocess.CompletedProcess(
                    ["python", "fake_verify.py"],
                    0,
                    stdout=json.dumps({"ok": True, "result": {"status": "passed"}}),
                    stderr="",
                ),
            )

            self.assertEqual(payload["status"], "restored_and_verified")
            self.assertEqual(script_path.read_text(encoding="utf-8"), "original\n")
            self.assertTrue(Path(payload["artifact_file"]).is_file())


if __name__ == "__main__":
    unittest.main()
