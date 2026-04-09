"""Legacy MCP bridge: fix loop rounds, stepwise ops, and live flow error/structure contracts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_pointer_cli(
    tool: str,
    args: dict,
    *,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    repo = _repo_root()
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [
            sys.executable,
            str(repo / "mcp" / "server.py"),
            "--tool",
            tool,
            "--args",
            json.dumps(args, ensure_ascii=False),
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _parse_stdout(proc: subprocess.CompletedProcess[str]) -> dict:
    raw = (proc.stdout or "").strip()
    if not raw:
        raise AssertionError(f"empty stdout stderr={proc.stderr!r}")
    return json.loads(raw)


def _assert_stable_error(case: unittest.TestCase, payload: dict) -> None:
    case.assertIn("ok", payload)
    case.assertFalse(payload.get("ok"))
    err = payload.get("error")
    case.assertIsInstance(err, dict)
    case.assertIn("code", err)
    case.assertIsInstance(err["code"], str)
    case.assertTrue(err["code"].strip())
    case.assertIn("message", err)
    case.assertIsInstance(err["message"], str)


class LegacyStepwiseFixloopLiveTests(unittest.TestCase):
    def test_resume_fix_loop_not_found_is_stable_error(self) -> None:
        proc = _run_pointer_cli(
            "resume_fix_loop",
            {"run_id": "nonexistent-run-id-legacy-test", "project_root": str(_repo_root())},
        )
        payload = _parse_stdout(proc)
        _assert_stable_error(self, payload)
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")
        self.assertIn("details", payload["error"])

    def test_resume_fix_loop_terminal_success_has_fix_loop_rounds(self) -> None:
        repo = _repo_root()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_id = "legacy_fixloop_terminal_ok"
            run_root = base / run_id
            run_root.mkdir(parents=True)
            artifact_posix = run_root.resolve().as_posix()
            state = {
                "version": 2,
                "run_id": run_id,
                "artifact_root": artifact_posix,
                "status": "resolved",
                "current_step": "resolved",
                "fix_loop_round": 1,
                "approval_required": False,
                "fix_loop": {
                    "enabled": True,
                    "max_rounds": 3,
                    "rounds_executed": 1,
                    "approval_required": False,
                    "status": "resolved",
                    "rounds": [
                        {
                            "round": 0,
                            "run_id": run_id,
                            "status": "failed",
                            "reason": "contract_test_initial",
                            "primary_failure": {"category": "test", "expected": "ok", "actual": "fail"},
                        },
                        {
                            "round": 1,
                            "run_id": run_id,
                            "status": "passed",
                            "reason": "contract_test_retry",
                            "primary_failure": {},
                        },
                    ],
                },
            }
            (run_root / "fix_loop_state.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            proc = _run_pointer_cli(
                "resume_fix_loop",
                {
                    "run_id": run_id,
                    "project_root": str(repo),
                    "artifact_base": str(base.resolve()),
                },
            )
            payload = _parse_stdout(proc)
            self.assertTrue(payload.get("ok"), msg=payload)
            result = payload.get("result", {})
            self.assertIsInstance(result, dict)
            fl = result.get("fix_loop")
            self.assertIsInstance(fl, dict)
            self.assertIn("rounds", fl)
            self.assertIsInstance(fl["rounds"], list)
            self.assertGreaterEqual(len(fl["rounds"]), 1)
            for key in ("enabled", "max_rounds", "rounds_executed", "status"):
                self.assertIn(key, fl)

    def test_resume_fix_loop_exhausted_terminal_has_rounds(self) -> None:
        repo = _repo_root()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_id = "legacy_fixloop_terminal_exhausted"
            run_root = base / run_id
            run_root.mkdir(parents=True)
            state = {
                "version": 2,
                "run_id": run_id,
                "artifact_root": run_root.resolve().as_posix(),
                "status": "exhausted",
                "current_step": "exhausted",
                "fix_loop_round": 2,
                "approval_required": False,
                "fix_loop": {
                    "enabled": True,
                    "max_rounds": 2,
                    "rounds_executed": 2,
                    "approval_required": False,
                    "status": "exhausted",
                    "stop_reason": "max_rounds",
                    "rounds": [{"round": 2, "status": "failed", "reason": "still_failing"}],
                },
            }
            (run_root / "fix_loop_state.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            proc = _run_pointer_cli(
                "resume_fix_loop",
                {"run_id": run_id, "project_root": str(repo), "artifact_base": str(base.resolve())},
            )
            payload = _parse_stdout(proc)
            self.assertTrue(payload.get("ok"), msg=payload)
            result = payload.get("result", {})
            fl = result.get("fix_loop", {})
            self.assertIsInstance(fl.get("rounds"), list)

    def test_start_stepwise_flow_broadcast_gate_stable_error(self) -> None:
        proc = _run_pointer_cli(
            "start_stepwise_flow",
            {"project_root": str(_repo_root()), "flow_file": "flows/internal/contract_force_fail_invalid_scene.json"},
        )
        payload = _parse_stdout(proc)
        _assert_stable_error(self, payload)
        self.assertEqual(payload["error"]["code"], "BROADCAST_ENTRY_REQUIRED")

    def test_start_stepwise_flow_missing_flow_stable_error(self) -> None:
        proc = _run_pointer_cli(
            "start_stepwise_flow",
            {
                "project_root": str(_repo_root()),
                "flow_file": "__missing_legacy_stepwise__.json",
                "allow_non_broadcast": True,
            },
            env_extra={"MCP_ALLOW_NON_BROADCAST": "1"},
        )
        payload = _parse_stdout(proc)
        _assert_stable_error(self, payload)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_prepare_step_execute_step_verify_step_step_once_stable_errors(self) -> None:
        env = {"MCP_ALLOW_NON_BROADCAST": "1"}
        bypass = {"allow_non_broadcast": True}
        for tool in ("prepare_step", "execute_step", "verify_step"):
            proc = _run_pointer_cli(
                tool,
                {"project_root": str(_repo_root()), "run_id": "", **bypass},
                env_extra=env,
            )
            payload = _parse_stdout(proc)
            _assert_stable_error(self, payload)
            self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

        proc2 = _run_pointer_cli(
            "prepare_step",
            {"project_root": str(_repo_root()), "run_id": "no_such_stepwise_session", **bypass},
            env_extra=env,
        )
        p2 = _parse_stdout(proc2)
        _assert_stable_error(self, p2)
        self.assertEqual(p2["error"]["code"], "NOT_FOUND")

        proc3 = _run_pointer_cli(
            "step_once",
            {"project_root": str(_repo_root()), "run_id": "", **bypass},
            env_extra=env,
        )
        p3 = _parse_stdout(proc3)
        _assert_stable_error(self, p3)
        self.assertEqual(p3["error"]["code"], "INVALID_ARGUMENT")

    def test_start_game_flow_live_missing_flow_stable_error(self) -> None:
        proc = _run_pointer_cli(
            "start_game_flow_live",
            {
                "project_root": str(_repo_root()),
                "flow_file": "__missing_live_flow__.json",
                "allow_non_broadcast": True,
            },
            env_extra={"MCP_ALLOW_NON_BROADCAST": "1"},
        )
        payload = _parse_stdout(proc)
        _assert_stable_error(self, payload)
        self.assertIn(payload["error"]["code"], ("INVALID_ARGUMENT", "NOT_FOUND"))

    def test_get_live_flow_progress_missing_run_id_stable_error(self) -> None:
        proc = _run_pointer_cli(
            "get_live_flow_progress",
            {"project_root": str(_repo_root()), "run_id": ""},
        )
        payload = _parse_stdout(proc)
        _assert_stable_error(self, payload)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_get_live_flow_progress_pending_minimal_structure(self) -> None:
        proc = _run_pointer_cli(
            "get_live_flow_progress",
            {"project_root": str(_repo_root()), "run_id": "pending-nonexistent-live-legacy"},
        )
        payload = _parse_stdout(proc)
        self.assertTrue(payload.get("ok"), msg=payload)
        result = payload.get("result", {})
        self.assertEqual(result.get("run_id"), "pending-nonexistent-live-legacy")
        self.assertIn("state", result)

    def test_run_and_stream_flow_missing_flow_stable_error(self) -> None:
        proc = _run_pointer_cli(
            "run_and_stream_flow",
            {
                "project_root": str(_repo_root()),
                "flow_file": "__missing_stream_flow__.json",
                "allow_non_broadcast": True,
                "max_wait_sec": 1,
            },
            env_extra={"MCP_ALLOW_NON_BROADCAST": "1"},
        )
        payload = _parse_stdout(proc)
        _assert_stable_error(self, payload)
        self.assertIn(payload["error"]["code"], ("INVALID_ARGUMENT", "NOT_FOUND"))


if __name__ == "__main__":
    unittest.main()
