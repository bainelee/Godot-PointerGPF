from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from driver_client import DriverClient
from flow_path_resolver import resolve_flow_path
from flow_parser import parse_flow_file
from flow_runner import _expand_steps, _to_driver_steps
from runtime_lock import acquire_runtime_lock, release_runtime_lock
from runner import GameTestRunner, RunRequest
from server_common import live_run_id, resolve_godot_bin, to_posix
from server_errors import AppError


class StepwiseOpsHandlersMixin:
    @staticmethod
    def _short_run_id_seed(flow_file: Path) -> str:
        stem = str(flow_file.stem or "flow").strip().lower()
        safe = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
        if not safe:
            safe = "flow"
        return safe[:24]

    def _detect_running_stepwise_session(self, project_root: Path) -> dict[str, Any]:
        artifact_base = project_root / "artifacts" / "test-runs"
        if not artifact_base.exists() or not artifact_base.is_dir():
            return {}
        for run_root in sorted(artifact_base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not run_root.is_dir():
                continue
            state_path = run_root / "stepwise_session.json"
            if not state_path.exists():
                continue
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if str(payload.get("status", "")).strip().lower() != "running":
                continue
            pid = int(payload.get("pid", 0) or 0)
            if pid > 0 and self._is_pid_running(pid):
                return {
                    "run_id": str(payload.get("run_id", "")),
                    "pid": pid,
                    "artifact_root": str(run_root),
                }
        return {}

    @staticmethod
    def _extract_game_time(response: dict[str, Any]) -> str:
        if not isinstance(response, dict):
            return ""
        direct_keys = ("game_time", "sim_day", "simDay", "day", "time")
        for key in direct_keys:
            val = response.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        data = response.get("data")
        if isinstance(data, dict):
            for key in direct_keys:
                val = data.get(key)
                if val is not None and str(val).strip():
                    return str(val).strip()
        return ""

    @staticmethod
    def _apply_wait_scale(driver_steps: list[dict[str, Any]], wait_scale: float) -> list[dict[str, Any]]:
        if wait_scale <= 0:
            return driver_steps
        if abs(wait_scale - 1.0) < 1e-6:
            return driver_steps
        scaled_steps: list[dict[str, Any]] = []
        for step in driver_steps:
            if not isinstance(step, dict):
                continue
            cloned = dict(step)
            action = str(cloned.get("action", "")).strip()
            params = cloned.get("params", {})
            if not isinstance(params, dict):
                params = {}
            params = dict(params)
            if action == "sleep":
                ms = int(params.get("ms", 0) or 0)
                if ms > 0:
                    params["ms"] = max(1, int(ms * wait_scale))
            elif action == "wait":
                timeout_ms = int(params.get("timeoutMs", 0) or 0)
                if timeout_ms > 0:
                    params["timeoutMs"] = max(50, int(timeout_ms * wait_scale))
                until = params.get("until")
                if isinstance(until, dict):
                    until_copy = dict(until)
                    until_timeout = int(until_copy.get("timeoutMs", 0) or 0)
                    if until_timeout > 0:
                        until_copy["timeoutMs"] = max(50, int(until_timeout * wait_scale))
                    params["until"] = until_copy
            cloned["params"] = params
            timeout_sec = int(cloned.get("timeoutSec", 0) or 0)
            if timeout_sec > 0 and action in {"sleep", "wait"}:
                cloned["timeoutSec"] = max(1, int(timeout_sec * wait_scale))
            scaled_steps.append(cloned)
        return scaled_steps

    def start_stepwise_flow(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_root_raw = arguments.get("project_root", str(self.default_project_root))
        project_root = Path(str(project_root_raw)).resolve()
        if not project_root.exists():
            raise AppError("INVALID_ARGUMENT", f"project_root not found: {project_root}")
        allow_parallel = bool(arguments.get("allow_parallel", False))
        if not allow_parallel:
            running = self._detect_running_stepwise_session(project_root)
            if running:
                raise AppError(
                    "STEPWISE_SESSION_ACTIVE",
                    "another stepwise session is still running; wait for it to finish before starting a new one",
                    running,
                )
        flow_file_raw = str(arguments.get("flow_file", "")).strip()
        if not flow_file_raw:
            raise AppError("INVALID_ARGUMENT", "flow_file is required")
        flow_file = resolve_flow_path(project_root=project_root, raw_flow_file=flow_file_raw)
        if not flow_file.exists():
            raise AppError("INVALID_ARGUMENT", f"flow_file not found: {flow_file}")
        requested_godot_bin = str(arguments.get("godot_bin", "godot4"))
        godot_bin, resolution_meta = resolve_godot_bin(
            requested=requested_godot_bin,
            strict=bool(arguments.get("strict_godot_bin", False)),
            allow_unresolved=False,
            project_root=project_root,
        )
        flow = parse_flow_file(flow_file)
        flow_steps = _expand_steps(flow, flow_file)
        default_step_timeout_sec = int(flow.get("flowStepTimeoutSec", 15))
        driver_steps = _to_driver_steps(flow_steps, default_timeout_sec=default_step_timeout_sec)
        wait_scale = float(arguments.get("wait_scale", 1.0) or 1.0)
        driver_steps = self._apply_wait_scale(driver_steps, wait_scale=wait_scale)
        if not driver_steps:
            raise AppError("INVALID_ARGUMENT", "flow has no executable steps")
        runner = GameTestRunner(project_root=project_root)
        run_id = str(arguments.get("run_id", "")).strip() or live_run_id(f"{self._short_run_id_seed(flow_file)}_sw")
        run_root = runner._prepare_artifacts(run_id)
        user_data_dir_raw = str(arguments.get("user_data_dir", "")).strip()
        if user_data_dir_raw:
            user_data_dir = Path(user_data_dir_raw).resolve()
            user_data_dir.mkdir(parents=True, exist_ok=True)
        else:
            user_data_dir = run_root / "user_data"
        session = run_id
        req = RunRequest(
            system=str(flow.get("system", "gameplay")),
            project_root=project_root,
            scenario=str(flow.get("scenario", "flow")),
            profile=str(flow.get("profile", "regression")),
            mode=str(flow.get("mode", "local")),
            timeout_sec=int(arguments.get("timeout_sec", 300)),
            retry=0,
            godot_bin=godot_bin,
            scene=str(flow.get("scene", "")) or None,
            dry_run=False,
            enable_test_driver=True,
            flow_steps=[],
            flow_step_timeout_sec=default_step_timeout_sec,
            driver_ready_timeout_sec=int(flow.get("driverReadyTimeoutSec", 20)),
            driver_no_activity_timeout_sec=int(flow.get("driverNoActivityTimeoutSec", 5)),
            user_data_dir=user_data_dir,
            reload_project_before_run=bool(flow.get("reloadProjectBeforeRun", True)),
            reload_timeout_sec=int(flow.get("reloadTimeoutSec", 20)),
            test_driver_session=session,
            requested_run_id=run_id,
        )
        cmd = runner._build_command(req, run_root=run_root, test_driver_session=session)
        runner._reset_driver_ipc(user_data_dir, session)
        stdout_path = run_root / "logs" / "stepwise_stdout.log"
        stderr_path = run_root / "logs" / "stepwise_stderr.log"
        with stdout_path.open("w", encoding="utf-8", errors="replace") as out_fh, stderr_path.open(
            "w", encoding="utf-8", errors="replace"
        ) as err_fh:
            proc = subprocess.Popen(  # pylint: disable=consider-using-with
                cmd,
                cwd=str(project_root),
                stdout=out_fh,
                stderr=err_fh,
                text=True,
            )
        runtime_lock_acquired = False
        try:
            acquire_runtime_lock(
                project_root=project_root,
                pid=int(proc.pid),
                run_id=run_id,
                owner="stepwise",
                allow_parallel=allow_parallel,
            )
            runtime_lock_acquired = True
        except RuntimeError as exc:
            self._terminate_pid(int(proc.pid))
            raise AppError("TEST_RUNTIME_ACTIVE", f"another test runtime is active: {exc}")
        try:
            session_safe = run_id
            candidate_dirs = runner._candidate_user_data_dirs(user_data_dir)
            driver_dirs: list[Path] = []
            for root in candidate_dirs:
                d = root / "test_driver" / session_safe
                d.mkdir(parents=True, exist_ok=True)
                driver_dirs.append(d)
            ready_deadline = time.monotonic() + max(1.0, float(req.driver_ready_timeout_sec))
            active_driver_dir: Optional[Path] = None
            while time.monotonic() <= ready_deadline:
                if proc.poll() is not None:
                    raise AppError("INVALID_STATE", f"test process exited before ready (exit={proc.returncode})")
                for d in driver_dirs:
                    resp_file = d / "response.json"
                    if not resp_file.exists():
                        continue
                    try:
                        data = json.loads(resp_file.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if data.get("status") == "ready":
                        active_driver_dir = d
                        break
                if active_driver_dir is not None:
                    break
                time.sleep(0.05)
            if active_driver_dir is None:
                self._terminate_pid(int(proc.pid))
                raise AppError("INVALID_STATE", "test driver did not become ready in time")
        except Exception:
            if runtime_lock_acquired:
                release_runtime_lock(project_root, int(proc.pid))
            self._terminate_pid(int(proc.pid))
            raise
        state = {
            "version": 1,
            "mode": "stepwise",
            "run_id": run_id,
            "flow_id": str(flow.get("flowId", flow_file.stem)),
            "flow_file": str(flow_file),
            "project_root": str(project_root),
            "run_root": str(run_root),
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": "",
            "pid": int(proc.pid),
            "session": session,
            "driver_dir": str(active_driver_dir),
            "user_data_dir": str(user_data_dir),
            "driver_steps": driver_steps,
            "step_results": [],
            "current_index": 0,
            "prepared_index": -1,
            "awaiting_verify": False,
            "last_execution": {},
            "last_step_id": "",
            "pid_exit_verified": False,
            "last_error": "",
            "runtime_lock_acquired": runtime_lock_acquired,
        }
        self._write_stepwise_flow_report(run_root, state)
        self._save_stepwise_state(run_root, state)
        first = driver_steps[0] if driver_steps else {}
        return {
            "run_id": run_id,
            "status": "running",
            "mode": "stepwise",
            "total_steps": len(driver_steps),
            "current_index": 0,
            "next_step": first,
            "artifact_root": to_posix(run_root),
            "wait_scale": wait_scale,
            "godot_bin_requested": requested_godot_bin,
            "godot_bin_resolved": godot_bin,
            "godot_bin_resolution": resolution_meta,
        }

    def prepare_step(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        run_root = self._resolve_run_root(run_id, arguments)
        state = self._load_stepwise_state(run_root)
        if not state or str(state.get("mode", "")) != "stepwise":
            raise AppError("NOT_FOUND", f"stepwise session not found for run_id: {run_id}")
        if str(state.get("status", "")) != "running":
            return {"run_id": run_id, "status": str(state.get("status", "")), "message": "session not running"}
        if bool(state.get("awaiting_verify", False)):
            raise AppError("INVALID_STATE", "previous step executed; call verify_step before preparing next step")
        current = int(state.get("current_index", 0))
        driver_steps = state.get("driver_steps", [])
        if not isinstance(driver_steps, list) or current >= len(driver_steps):
            return {"run_id": run_id, "status": "finished", "message": "no remaining step"}
        step = driver_steps[current] if isinstance(driver_steps[current], dict) else {}
        if int(state.get("prepared_index", -1)) != current:
            self._append_stepwise_event(
                run_root,
                {
                    "type": "step_ready",
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "index": current,
                    "step_id": str(step.get("id", "")),
                    "action": str(step.get("action", "")),
                },
            )
            state["prepared_index"] = current
            self._save_stepwise_state(run_root, state)
        return {
            "run_id": run_id,
            "status": "ready",
            "step_index": current,
            "step_total": len(driver_steps),
            "step": step,
            "chat_events": [
                self._build_stepwise_chat_event(
                    phase="about_to_start",
                    step_id=str(step.get("id", "")),
                    action=str(step.get("action", "")),
                    step_index=current,
                    step_total=len(driver_steps),
                    status="ready",
                )
            ],
        }

    def execute_step(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        run_root = self._resolve_run_root(run_id, arguments)
        state = self._load_stepwise_state(run_root)
        if not state or str(state.get("mode", "")) != "stepwise":
            raise AppError("NOT_FOUND", f"stepwise session not found for run_id: {run_id}")
        if str(state.get("status", "")) != "running":
            raise AppError("INVALID_STATE", f"session not running: {state.get('status', '')}")
        if bool(state.get("awaiting_verify", False)):
            raise AppError("INVALID_STATE", "call verify_step before executing next step")
        current = int(state.get("current_index", 0))
        prepared = int(state.get("prepared_index", -1))
        driver_steps = state.get("driver_steps", [])
        if not isinstance(driver_steps, list) or current >= len(driver_steps):
            raise AppError("INVALID_STATE", "no remaining step")
        if prepared != current:
            raise AppError("INVALID_STATE", "step not prepared; call prepare_step first")
        step = driver_steps[current] if isinstance(driver_steps[current], dict) else {}
        step_id = str(step.get("id", ""))
        action = str(step.get("action", ""))
        params = step.get("params", {})
        if not isinstance(params, dict):
            params = {}
        timeout_sec = float(step.get("timeoutSec", 15))
        pid = int(state.get("pid", 0) or 0)
        if pid > 0 and not self._is_pid_running(pid):
            self._finalize_stepwise_session(run_root, state, final_status="failed", error="godot process exited before step execution")
            return {
                "run_id": run_id,
                "status": "finished",
                "flow_status": "failed",
                "step_index": current,
                "step_total": len(driver_steps),
                "step_id": step_id,
                "action": action,
                "execution_status": "failed",
                "duration_ms": 0,
                "response": {"status": "error", "error": {"message": "godot process exited before step execution"}},
                "chat_events": [
                    self._build_stepwise_chat_event(
                        phase="started",
                        step_id=step_id,
                        action=action,
                        step_index=current,
                        step_total=len(driver_steps),
                        status="running",
                    ),
                    self._build_stepwise_chat_event(
                        phase="result",
                        step_id=step_id,
                        action=action,
                        step_index=current,
                        step_total=len(driver_steps),
                        status="failed",
                        detail="godot process exited before step execution",
                    ),
                ],
            }
        self._append_stepwise_event(
            run_root,
            {
                "type": "step_started",
                "ts": datetime.now(timezone.utc).isoformat(),
                "index": current,
                "step_id": step_id,
                "action": action,
            },
        )
        started = time.time()
        try:
            client = DriverClient(base_dir=Path(str(state.get("driver_dir", ""))))
            response = client.send_and_wait(action=action, params=params, timeout_sec=timeout_sec)
            ok = str(response.get("status", "")) == "ok"
            status = "passed" if ok else "failed"
        except Exception as exc:  # pylint: disable=broad-except
            response = {"status": "error", "error": {"message": str(exc)}}
            status = "failed"
        duration_ms = int((time.time() - started) * 1000)
        state["awaiting_verify"] = True
        state["last_execution"] = {
            "index": current,
            "step_id": step_id,
            "action": action,
            "status": status,
            "response": response,
            "duration_ms": duration_ms,
            "game_time": self._extract_game_time(response),
        }
        state["last_step_id"] = step_id
        self._save_stepwise_state(run_root, state)
        return {
            "run_id": run_id,
            "status": "executed",
            "step_index": current,
            "step_total": len(driver_steps),
            "step_id": step_id,
            "action": action,
            "execution_status": status,
            "duration_ms": duration_ms,
            "response": response,
            "chat_events": [
                self._build_stepwise_chat_event(
                    phase="started",
                    step_id=step_id,
                    action=action,
                    step_index=current,
                    step_total=len(driver_steps),
                    status="running",
                ),
                self._build_stepwise_chat_event(
                    phase="result",
                    step_id=step_id,
                    action=action,
                    step_index=current,
                    step_total=len(driver_steps),
                    status=status,
                    detail=str(response.get("error", {}).get("message", "")) if isinstance(response.get("error"), dict) else "",
                    game_time=self._extract_game_time(response),
                ),
            ],
        }

    def verify_step(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        run_root = self._resolve_run_root(run_id, arguments)
        state = self._load_stepwise_state(run_root)
        if not state or str(state.get("mode", "")) != "stepwise":
            raise AppError("NOT_FOUND", f"stepwise session not found for run_id: {run_id}")
        if not bool(state.get("awaiting_verify", False)):
            raise AppError("INVALID_STATE", "no executed step awaiting verify")
        last = state.get("last_execution", {})
        if not isinstance(last, dict):
            raise AppError("INVALID_STATE", "invalid last execution state")
        idx = int(last.get("index", -1))
        step_id = str(last.get("step_id", ""))
        action = str(last.get("action", ""))
        status = str(last.get("status", "failed"))
        response = last.get("response", {})
        if not isinstance(response, dict):
            response = {}
        game_time = str(last.get("game_time", "")).strip() or self._extract_game_time(response)
        verified = status == "passed"
        verify_reason = "driver response status == ok" if verified else "driver response indicates failure"
        screenshot_abs = ""
        if verified and action == "screenshot":
            raw_path = str(response.get("screenshot", "")).strip()
            data = response.get("data", {})
            if not raw_path and isinstance(data, dict):
                raw_path = str(data.get("screenshot", data.get("path", ""))).strip()
            user_data_dir = Path(str(state.get("user_data_dir", "")))
            fallback_user_data_dir = Path("")
            driver_dir_raw = str(state.get("driver_dir", "")).strip()
            if driver_dir_raw:
                try:
                    driver_dir = Path(driver_dir_raw)
                    fallback_user_data_dir = driver_dir.parent.parent
                except Exception:
                    fallback_user_data_dir = Path("")
            if raw_path.startswith("user://"):
                rel = raw_path.replace("user://", "", 1).replace("\\", "/")
                candidate = user_data_dir / rel
                if not candidate.exists() and str(fallback_user_data_dir):
                    candidate = fallback_user_data_dir / rel
            else:
                candidate = Path(raw_path) if raw_path else Path("")
            screenshot_abs = str(candidate.resolve()) if str(candidate) else ""
            if not screenshot_abs or not Path(screenshot_abs).exists():
                verified = False
                verify_reason = f"screenshot file missing: {raw_path or 'empty path'}"
        completed_status = "passed" if verified else "failed"
        self._append_stepwise_event(
            run_root,
            {
                "type": "step_completed",
                "ts": datetime.now(timezone.utc).isoformat(),
                "index": idx,
                "step_id": step_id,
                "action": action,
                "status": completed_status,
                "duration_ms": int(last.get("duration_ms", 0)),
                "verify_reason": verify_reason,
            },
        )
        step_results = state.get("step_results", [])
        if not isinstance(step_results, list):
            step_results = []
        step_results.append(
            {
                "step_id": step_id,
                "action": action,
                "status": completed_status,
                "response": response,
                "duration_ms": int(last.get("duration_ms", 0)),
            }
        )
        state["step_results"] = step_results
        self._write_stepwise_driver_flow(run_root, step_results)
        driver_steps = state.get("driver_steps", [])
        total = len(driver_steps) if isinstance(driver_steps, list) else 0
        state["awaiting_verify"] = False
        state["prepared_index"] = -1
        state["last_execution"] = {}
        if verified:
            state["current_index"] = idx + 1
            if int(state.get("current_index", 0)) >= total:
                self._finalize_stepwise_session(run_root, state, final_status="passed")
                return {
                    "run_id": run_id,
                    "verified": True,
                    "status": "finished",
                    "flow_status": "passed",
                    "step_index": idx,
                    "step_total": total,
                    "verify_reason": verify_reason,
                    "screenshot_path": screenshot_abs,
                    "chat_events": [
                        self._build_stepwise_chat_event(
                            phase="verify",
                            step_id=step_id,
                            action=action,
                            step_index=idx,
                            step_total=total,
                            status="passed",
                            detail=verify_reason,
                            game_time=game_time,
                        )
                    ],
                }
            state["status"] = "running"
            self._write_stepwise_flow_report(run_root, state)
            self._save_stepwise_state(run_root, state)
            next_idx = int(state.get("current_index", 0))
            next_step = driver_steps[next_idx] if isinstance(driver_steps, list) and next_idx < len(driver_steps) else {}
            return {
                "run_id": run_id,
                "verified": True,
                "status": "running",
                "step_index": idx,
                "step_total": total,
                "verify_reason": verify_reason,
                "screenshot_path": screenshot_abs,
                "next_step": next_step,
                "chat_events": [
                    self._build_stepwise_chat_event(
                        phase="verify",
                        step_id=step_id,
                        action=action,
                        step_index=idx,
                        step_total=total,
                        status="passed",
                        detail=verify_reason,
                        game_time=game_time,
                    )
                ],
            }
        state["status"] = "failed"
        self._finalize_stepwise_session(run_root, state, final_status="failed", error=verify_reason)
        return {
            "run_id": run_id,
            "verified": False,
            "status": "finished",
            "flow_status": "failed",
            "step_index": idx,
            "step_total": total,
            "verify_reason": verify_reason,
            "screenshot_path": screenshot_abs,
            "chat_events": [
                self._build_stepwise_chat_event(
                    phase="verify",
                    step_id=step_id,
                    action=action,
                    step_index=idx,
                    step_total=total,
                    status="failed",
                    detail=verify_reason,
                    game_time=game_time,
                )
            ],
        }

    def step_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Atomic step gate: prepare -> execute -> verify in one call."""
        run_id = str(arguments.get("run_id", "")).strip()
        if not run_id:
            raise AppError("INVALID_ARGUMENT", "run_id is required")
        t0 = time.perf_counter()
        prepare = self.prepare_step({"run_id": run_id})
        if str(prepare.get("status", "")) == "finished":
            return {
                "run_id": run_id,
                "status": "finished",
                "flow_status": "passed",
                "stage_events": [],
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
        execute = self.execute_step({"run_id": run_id})
        verify = self.verify_step({"run_id": run_id})
        stage_events: list[dict[str, Any]] = []
        stage_events.extend(prepare.get("chat_events", []) if isinstance(prepare.get("chat_events"), list) else [])
        stage_events.extend(execute.get("chat_events", []) if isinstance(execute.get("chat_events"), list) else [])
        stage_events.extend(verify.get("chat_events", []) if isinstance(verify.get("chat_events"), list) else [])
        out: dict[str, Any] = {
            "run_id": run_id,
            "status": str(verify.get("status", "running")),
            "flow_status": str(verify.get("flow_status", "running" if bool(verify.get("verified", False)) else "failed")),
            "verified": bool(verify.get("verified", False)),
            "step_index": int(prepare.get("step_index", -1)),
            "step_total": int(prepare.get("step_total", 0)),
            "step": prepare.get("step", {}),
            "execution_status": str(execute.get("execution_status", "")),
            "verify_reason": str(verify.get("verify_reason", "")),
            "screenshot_path": str(verify.get("screenshot_path", "")),
            "next_step": verify.get("next_step", {}),
            "stage_events": stage_events,
            "game_time": stage_events[-1].get("game_time", "") if stage_events else "",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        }
        return out
