import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_evidence_plan import load_model_evidence_plan


class BugEvidencePlanTests(unittest.TestCase):
    def test_load_model_evidence_plan_accepts_bounded_sample_and_check_steps(self) -> None:
        plan = {
            "steps": [
                {
                    "id": "sample_enemy_modulate",
                    "phase": "post_trigger",
                    "action": "sample",
                    "target": {"hint": "node_name:Enemy"},
                    "metric": {"kind": "node_property", "property_path": "modulate"},
                    "windowMs": 400,
                    "intervalMs": 50,
                    "evidenceKey": "enemy_modulate_window",
                },
                {
                    "id": "check_enemy_modulate_changed",
                    "phase": "final_check",
                    "action": "check",
                    "checkType": "node_property_changes_within_window",
                    "evidenceRef": "enemy_modulate_window",
                    "predicate": {"operator": "changed_from_baseline"},
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = load_model_evidence_plan(
                Path(tmp),
                argparse.Namespace(evidence_plan_json=json.dumps(plan), evidence_plan_file=""),
            )

        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["plan"]["steps"][0]["source"], "model_evidence_plan")
        self.assertEqual(payload["plan"]["steps"][1]["modelEvidencePhase"], "final_check")

    def test_load_model_evidence_plan_rejects_unbounded_sample_window(self) -> None:
        plan = {
            "steps": [
                {
                    "id": "sample_forever",
                    "action": "sample",
                    "target": {"hint": "node_name:Enemy"},
                    "metric": {"kind": "node_property", "property_path": "modulate"},
                    "windowMs": 999999,
                    "intervalMs": 50,
                    "evidenceKey": "enemy_modulate_window",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = load_model_evidence_plan(
                Path(tmp),
                argparse.Namespace(evidence_plan_json=json.dumps(plan), evidence_plan_file=""),
            )

        self.assertEqual(payload["status"], "rejected")
        self.assertTrue(any("windowMs" in reason for reason in payload["rejected_reasons"]))

    def test_load_model_evidence_plan_accepts_trigger_window_observe(self) -> None:
        plan = {
            "steps": [
                {
                    "id": "observe_hit_signal",
                    "phase": "trigger_window",
                    "action": "observe",
                    "target": {"hint": "node_name:Enemy"},
                    "event": {"kind": "signal_emitted", "signal_name": "hit_taken"},
                    "windowMs": 400,
                    "evidenceKey": "enemy_hit_signal",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = load_model_evidence_plan(
                Path(tmp),
                argparse.Namespace(evidence_plan_json=json.dumps(plan), evidence_plan_file=""),
            )

        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["plan"]["steps"][0]["phase"], "trigger_window")

    def test_load_model_evidence_plan_rejects_unbounded_observe_window(self) -> None:
        plan = {
            "steps": [
                {
                    "id": "observe_hit_signal",
                    "phase": "trigger_window",
                    "action": "observe",
                    "target": {"hint": "node_name:Enemy"},
                    "event": {"kind": "signal_emitted", "signal_name": "hit_taken"},
                    "windowMs": 999999,
                    "evidenceKey": "enemy_hit_signal",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = load_model_evidence_plan(
                Path(tmp),
                argparse.Namespace(evidence_plan_json=json.dumps(plan), evidence_plan_file=""),
            )

        self.assertEqual(payload["status"], "rejected")
        self.assertTrue(any("observe windowMs" in reason for reason in payload["rejected_reasons"]))


if __name__ == "__main__":
    unittest.main()
