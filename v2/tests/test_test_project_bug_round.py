import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.test_project_bug_round import (
    record_bug_round_baseline,
    restore_bug_round_baseline,
    start_test_project_bug_round,
)


class TestProjectBugRoundTests(unittest.TestCase):
    def test_start_test_project_bug_round_records_baseline_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "main_menu_flow.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("extends Node\n", encoding="utf-8")

            args = type(
                "Args",
                (),
                {
                    "round_id": "round-001",
                    "files_to_record": "scripts/main_menu_flow.gd",
                    "location_scene": "",
                    "location_script": "",
                    "bug_kind": "",
                    "bug_summary": "summary",
                    "bug_report": "report",
                    "expected_behavior": "expected",
                    "steps_to_trigger": "step1|step2",
                    "location_node": "StartButton",
                },
            )()

            payload = start_test_project_bug_round(project_root, args)

            self.assertEqual(payload["status"], "round_started")
            manifest_path = Path(payload["baseline_manifest_file"])
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["files"][0]["res_path"], "res://scripts/main_menu_flow.gd")
            baseline_copy = Path(manifest["files"][0]["baseline_copy_absolute"])
            self.assertEqual(baseline_copy.read_text(encoding="utf-8"), "extends Node\n")

    def test_restore_bug_round_baseline_restores_original_file_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "main_menu_flow.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("original\n", encoding="utf-8")
            record_bug_round_baseline(project_root, "round-002", ["scripts/main_menu_flow.gd"])
            script_path.write_text("mutated\n", encoding="utf-8")

            payload = restore_bug_round_baseline(project_root, "round-002")

            self.assertEqual(payload["status"], "restored")
            self.assertEqual(script_path.read_text(encoding="utf-8"), "original\n")


if __name__ == "__main__":
    unittest.main()
