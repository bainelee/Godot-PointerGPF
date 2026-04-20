import argparse
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_repro_execution import run_bug_repro_flow


class BugReproExecutionTests(unittest.TestCase):
    def test_run_bug_repro_flow_marks_bug_not_reproduced_when_flow_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_set": {
                        "assertions": [
                            {"runtime_check": {"hint": "node_exists:GameLevel"}},
                        ]
                    },
                    "candidate_flow": {
                        "steps": [
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ]
                    },
                },
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {"execution": {"status": "passed"}}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

        self.assertEqual(payload["schema"], "pointer_gpf.v2.repro_run.v1")
        self.assertEqual(payload["status"], "bug_not_reproduced")
        self.assertFalse(payload["reproduction_confirmed"])

    def test_run_bug_repro_flow_marks_bug_reproduced_when_assertion_step_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_set": {
                        "assertions": [
                            {"runtime_check": {"hint": "node_exists:GameLevel"}},
                        ]
                    },
                    "candidate_flow": {
                        "steps": [
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ]
                    },
                },
                run_basic_flow_tool=lambda *_: (
                    2,
                    {
                        "ok": False,
                        "error": {
                            "code": "TIMEOUT",
                            "message": "bridge did not respond within step_timeout_ms",
                            "details": {"step_id": "wait_gamelevel"},
                        },
                    },
                    False,
                ),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

        self.assertEqual(payload["status"], "bug_reproduced")
        self.assertTrue(payload["reproduction_confirmed"])


if __name__ == "__main__":
    unittest.main()
