import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_fix_proposal import apply_validated_fix_proposal, load_fix_proposal


class BugFixProposalTests(unittest.TestCase):
    def test_example_fix_proposal_safe_replace_applies_and_rejected_examples_reject(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        examples_dir = repo_root / "v2" / "examples"
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "enemies" / "test_enemy.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(
                "extends Node\n\nfunc _sync_hits_to_shader():\n\treturn  # gpf_seeded_bug:hit_feedback_shader_not_updated\n\t_sync_ok()\n\nfunc _other():\n\tpass\n",
                encoding="utf-8",
            )
            fix_plan = {
                "candidate_files": [
                    {
                        "path": "res://scripts/enemies/test_enemy.gd",
                        "absolute_path": str(script_path),
                    }
                ]
            }

            safe = json.loads((examples_dir / "fix_proposal_safe_replace_example.json").read_text(encoding="utf-8"))
            safe_payload = apply_validated_fix_proposal(project_root, fix_plan, safe)

            mismatch = json.loads(
                (examples_dir / "fix_proposal_rejected_candidate_mismatch_example.json").read_text(encoding="utf-8")
            )
            mismatch_payload = apply_validated_fix_proposal(project_root, fix_plan, mismatch)

            broad = json.loads((examples_dir / "fix_proposal_rejected_broad_edit_example.json").read_text(encoding="utf-8"))
            broad_payload = apply_validated_fix_proposal(project_root, fix_plan, broad)

        self.assertEqual(safe_payload["status"], "fix_applied")
        self.assertEqual(mismatch_payload["status"], "fix_proposal_rejected")
        self.assertIn("candidate_file is not present", mismatch_payload["message"])
        self.assertEqual(broad_payload["status"], "fix_proposal_rejected")
        self.assertIn("find text must appear exactly once", broad_payload["message"])

    def test_hud_spawn_fix_proposal_restores_pointer_hud_spawn(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        examples_dir = repo_root / "v2" / "examples"
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            script_path = project_root / "scripts" / "game_level.gd"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(
                "extends Node3D\n\nconst POINTER_HUD := preload(\"res://scenes/ui/game_pointer_hud.tscn\")\n\nfunc _ready() -> void:\n\tpass  # gpf_seeded_bug:pointer_hud_not_spawned\n",
                encoding="utf-8",
            )
            fix_plan = {
                "candidate_files": [
                    {
                        "path": "res://scripts/game_level.gd",
                        "absolute_path": str(script_path),
                    }
                ]
            }
            proposal = json.loads((examples_dir / "hud_spawn_fix_proposal.json").read_text(encoding="utf-8"))

            payload = apply_validated_fix_proposal(project_root, fix_plan, proposal)
            updated = script_path.read_text(encoding="utf-8")

        self.assertEqual(payload["status"], "fix_applied")
        self.assertIn("\tadd_child(POINTER_HUD.instantiate())", updated)
        self.assertNotIn("gpf_seeded_bug:pointer_hud_not_spawned", updated)

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
