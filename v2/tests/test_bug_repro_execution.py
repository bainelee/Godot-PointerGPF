import argparse
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_repro_execution import (
    load_repro_result,
    repro_result_path,
    repro_verification_path,
    rerun_bug_repro_flow,
    run_bug_repro_flow,
)


class BugReproExecutionTests(unittest.TestCase):
    def test_run_bug_repro_flow_marks_bug_not_reproduced_when_postconditions_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_coverage": [],
                    "unsupported_assertions": [],
                    "candidate_flow": {
                        "steps": [
                            {"id": "launch_game", "action": "launchGame"},
                            {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                            {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ]
                    },
                    "execution_contract": {
                        "setup_step_ids": ["launch_game"],
                        "precondition_step_ids": ["wait_startbutton"],
                        "trigger_step_ids": ["click_startbutton"],
                        "postcondition_step_ids": ["wait_gamelevel"],
                        "close_step_ids": ["close_project"],
                    },
                },
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {"execution": {"status": "passed"}}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )
            self.assertEqual(payload["status"], "bug_not_reproduced")
            self.assertFalse(payload["reproduction_confirmed"])
            self.assertTrue(repro_result_path(project_root).is_file())
            self.assertEqual(load_repro_result(project_root)["status"], "bug_not_reproduced")

    def test_run_bug_repro_flow_marks_precondition_failure_before_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_coverage": [],
                    "unsupported_assertions": [],
                    "candidate_flow": {
                        "steps": [
                            {"id": "launch_game", "action": "launchGame"},
                            {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                            {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ]
                    },
                    "execution_contract": {
                        "setup_step_ids": ["launch_game"],
                        "precondition_step_ids": ["wait_startbutton"],
                        "trigger_step_ids": ["click_startbutton"],
                        "postcondition_step_ids": ["wait_gamelevel"],
                        "close_step_ids": ["close_project"],
                    },
                },
                run_basic_flow_tool=lambda *_: (
                    2,
                    {
                        "ok": False,
                        "error": {
                            "code": "STEP_FAILED",
                            "message": "start button missing",
                            "details": {"step_id": "wait_startbutton"},
                        },
                    },
                    False,
                ),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

        self.assertEqual(payload["status"], "precondition_failed")
        self.assertFalse(payload["reproduction_confirmed"])
        self.assertEqual(payload["failed_phase"], "precondition")
        self.assertEqual(payload["next_action"], "inspect_precondition_failure")

    def test_run_bug_repro_flow_marks_bug_reproduced_when_postcondition_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_coverage": [],
                    "unsupported_assertions": [],
                    "candidate_flow": {
                        "steps": [
                            {"id": "launch_game", "action": "launchGame"},
                            {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                            {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                            {"id": "assert_scene_change", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ]
                    },
                    "execution_contract": {
                        "setup_step_ids": ["launch_game"],
                        "precondition_step_ids": ["wait_startbutton"],
                        "trigger_step_ids": ["click_startbutton"],
                        "postcondition_step_ids": ["assert_scene_change"],
                        "close_step_ids": ["close_project"],
                    },
                },
                run_basic_flow_tool=lambda *_: (
                    2,
                    {
                        "ok": False,
                        "error": {
                            "code": "TIMEOUT",
                            "message": "target scene never appeared",
                            "details": {"step_id": "assert_scene_change"},
                        },
                    },
                    False,
                ),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

        self.assertEqual(payload["status"], "bug_reproduced")
        self.assertTrue(payload["reproduction_confirmed"])
        self.assertEqual(payload["failed_phase"], "postcondition")

    def test_run_bug_repro_flow_marks_runtime_invalid_for_engine_stall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_coverage": [],
                    "unsupported_assertions": [],
                    "candidate_flow": {"steps": [{"id": "launch_game", "action": "launchGame"}]},
                    "execution_contract": {
                        "setup_step_ids": ["launch_game"],
                        "precondition_step_ids": [],
                        "trigger_step_ids": [],
                        "postcondition_step_ids": [],
                        "close_step_ids": [],
                    },
                },
                run_basic_flow_tool=lambda *_: (
                    2,
                    {
                        "ok": False,
                        "error": {
                            "code": "ENGINE_RUNTIME_STALLED",
                            "message": "runtime bridge stopped responding",
                            "details": {"step_id": "launch_game"},
                        },
                    },
                    False,
                ),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

        self.assertEqual(payload["status"], "runtime_invalid")
        self.assertFalse(payload["reproduction_confirmed"])
        self.assertEqual(payload["next_action"], "inspect_runtime_failure")

    def test_rerun_bug_repro_flow_requires_existing_repro_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            payload = rerun_bug_repro_flow(
                project_root,
                args,
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

        self.assertEqual(payload["status"], "verification_not_ready")
        self.assertEqual(payload["next_action"], "run_bug_repro_flow_first")
        self.assertEqual(payload["artifact_file"], "")

    def test_rerun_bug_repro_flow_reuses_saved_plan_and_writes_separate_verification_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            args = argparse.Namespace(execution_mode="play_mode")
            initial = run_bug_repro_flow(
                project_root,
                args,
                plan_bug_repro_flow_fn=lambda *_: {
                    "bug_summary": "summary",
                    "assertion_coverage": [],
                    "unsupported_assertions": [],
                    "candidate_flow": {
                        "steps": [
                            {"id": "launch_game", "action": "launchGame"},
                            {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                            {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                            {"id": "assert_scene_change", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "close_project", "action": "closeProject"},
                        ]
                    },
                    "execution_contract": {
                        "setup_step_ids": ["launch_game"],
                        "precondition_step_ids": ["wait_startbutton"],
                        "trigger_step_ids": ["click_startbutton"],
                        "postcondition_step_ids": ["assert_scene_change"],
                        "close_step_ids": ["close_project"],
                    },
                },
                run_basic_flow_tool=lambda *_: (
                    2,
                    {
                        "ok": False,
                        "error": {
                            "code": "TIMEOUT",
                            "message": "target scene never appeared",
                            "details": {"step_id": "assert_scene_change"},
                        },
                    },
                    False,
                ),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

            rerun = rerun_bug_repro_flow(
                project_root,
                args,
                run_basic_flow_tool=lambda *_: (0, {"ok": True, "result": {"execution": {"status": "passed"}}}, True),
                normalize_execution_mode=lambda raw: str(raw or "play_mode"),
            )

            self.assertEqual(initial["status"], "bug_reproduced")
            self.assertEqual(rerun["schema"], "pointer_gpf.v2.repro_rerun.v1")
            self.assertEqual(rerun["status"], "bug_not_reproduced")
            self.assertTrue(repro_result_path(project_root).name.endswith("last_bug_repro_result.json"))
            self.assertTrue(str(rerun["source_repro_artifact"]).endswith("last_bug_repro_result.json"))
            self.assertTrue(str(rerun["artifact_file"]).endswith("last_bug_fix_verification.json"))
            self.assertTrue(repro_verification_path(project_root).is_file())
            self.assertEqual(load_repro_result(project_root)["status"], "bug_reproduced")


if __name__ == "__main__":
    unittest.main()
