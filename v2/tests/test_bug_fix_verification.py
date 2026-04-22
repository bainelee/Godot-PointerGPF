import argparse
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_fix_verification import (
    bug_fix_regression_path,
    bug_fix_verification_path,
    run_bug_fix_regression,
    verify_bug_fix,
)


class _CompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class BugFixVerificationTests(unittest.TestCase):
    def test_run_bug_fix_regression_writes_result_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = run_bug_fix_regression(
                project_root,
                build_command=lambda root: ["python", "fake_regression.py", "--project-root", str(root)],
                subprocess_run=lambda *args, **kwargs: _CompletedProcess(0, '{"ok": true, "results": []}', ""),
            )

            self.assertEqual(payload["status"], "passed")
            self.assertTrue(bug_fix_regression_path(project_root).is_file())
            self.assertEqual(payload["command"][1], "fake_regression.py")

    def test_verify_bug_fix_stops_when_apply_step_did_not_change_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = verify_bug_fix(
                project_root,
                argparse.Namespace(),
                apply_bug_fix_fn=lambda *_: {
                    "schema": "pointer_gpf.v2.fix_apply.v1",
                    "bug_summary": "summary",
                    "status": "fix_not_applied",
                    "next_action": "inspect_candidate_files_and_edit_code",
                },
                rerun_bug_repro_flow_fn=lambda *_: (_ for _ in ()).throw(RuntimeError("should not run")),
                run_bug_fix_regression_fn=lambda *_: (_ for _ in ()).throw(RuntimeError("should not run")),
            )

            self.assertEqual(payload["status"], "fix_verification_not_ready")
            self.assertTrue(bug_fix_verification_path(project_root).is_file())

    def test_verify_bug_fix_stops_when_bug_focused_rerun_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = verify_bug_fix(
                project_root,
                argparse.Namespace(),
                apply_bug_fix_fn=lambda *_: {
                    "schema": "pointer_gpf.v2.fix_apply.v1",
                    "bug_summary": "summary",
                    "status": "fix_applied",
                },
                rerun_bug_repro_flow_fn=lambda *_: {
                    "schema": "pointer_gpf.v2.repro_rerun.v1",
                    "status": "bug_reproduced",
                    "next_action": "inspect_failure_before_fixing",
                },
                run_bug_fix_regression_fn=lambda *_: (_ for _ in ()).throw(RuntimeError("should not run")),
            )

            self.assertEqual(payload["status"], "fix_verification_failed")
            self.assertEqual(payload["next_action"], "inspect_failure_before_fixing")

    def test_verify_bug_fix_runs_regression_after_passing_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            payload = verify_bug_fix(
                project_root,
                argparse.Namespace(),
                apply_bug_fix_fn=lambda *_: {
                    "schema": "pointer_gpf.v2.fix_apply.v1",
                    "bug_summary": "summary",
                    "status": "fix_applied",
                },
                rerun_bug_repro_flow_fn=lambda *_: {
                    "schema": "pointer_gpf.v2.repro_rerun.v1",
                    "status": "bug_not_reproduced",
                },
                run_bug_fix_regression_fn=lambda root: {
                    "schema": "pointer_gpf.v2.fix_regression.v1",
                    "project_root": str(root),
                    "status": "passed",
                },
            )

            self.assertEqual(payload["status"], "fix_verified")
            self.assertEqual(payload["regression_result"]["status"], "passed")
            self.assertTrue(bug_fix_verification_path(project_root).is_file())


if __name__ == "__main__":
    unittest.main()
