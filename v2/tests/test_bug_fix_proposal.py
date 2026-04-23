import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_fix_proposal import apply_validated_fix_proposal, load_fix_proposal


class BugFixProposalTests(unittest.TestCase):
    def test_load_fix_proposal_accepts_json(self) -> None:
        proposal = {
            "candidate_file": "res://scripts/enemy.gd",
            "edits": [{"kind": "insert_after", "find": "func hit():", "text": "\n\tflash()"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = load_fix_proposal(
                Path(tmp),
                argparse.Namespace(fix_proposal_json=json.dumps(proposal), fix_proposal_file=""),
            )

        self.assertEqual(payload["status"], "loaded")
        self.assertEqual(payload["proposal"]["candidate_file"], "res://scripts/enemy.gd")

    def test_apply_validated_fix_proposal_applies_unique_insert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "enemy.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("extends Node\n\nfunc hit():\n\tpass\n", encoding="utf-8")
            fix_plan = {
                "candidate_files": [
                    {
                        "path": "res://scripts/enemy.gd",
                        "absolute_path": str(script_path),
                    }
                ]
            }
            proposal = {
                "candidate_file": "res://scripts/enemy.gd",
                "reason": "runtime evidence shows hit feedback did not change",
                "edits": [
                    {
                        "kind": "insert_after",
                        "find": "func hit():",
                        "text": "\n\tflash_hit_feedback()",
                    }
                ],
            }

            payload = apply_validated_fix_proposal(project_root, fix_plan, proposal)
            updated = script_path.read_text(encoding="utf-8")
            proposal_artifact_exists = Path(payload["proposal_artifact"]).is_file()
            application_artifact_exists = Path(payload["application_artifact"]).is_file()

        self.assertEqual(payload["status"], "fix_applied")
        self.assertIn("flash_hit_feedback()", updated)
        self.assertTrue(proposal_artifact_exists)
        self.assertTrue(application_artifact_exists)

    def test_apply_validated_fix_proposal_rejects_file_outside_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = apply_validated_fix_proposal(
                project_root,
                {"candidate_files": [{"path": "res://scripts/enemy.gd"}]},
                {
                    "candidate_file": "res://scripts/player.gd",
                    "edits": [{"kind": "insert_after", "find": "func hit():", "text": "\n\tflash()"}],
                },
            )

        self.assertEqual(payload["status"], "fix_proposal_rejected")
        self.assertIn("candidate_file is not present", payload["message"])


if __name__ == "__main__":
    unittest.main()
