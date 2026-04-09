from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flow_timeline_chat_map import human_step_and_goal
from runtime_lock import release_runtime_lock
from server_common import to_posix


class StepwiseSupportMixin:
    UNPAUSED_ACTION_WHITELIST: set[str] = {"wait", "sleep", "runsubflow"}

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "y", "on"}

    def _step_requires_unpaused(self, step: dict[str, Any]) -> bool:
        if not isinstance(step, dict):
            return False
        params = step.get("params", {})
        if not isinstance(params, dict):
            params = {}
        explicit = params.get("requires_unpaused")
        if explicit is not None:
            return self._to_bool(explicit)
        action = str(step.get("action", "")).strip().lower()
        return action in self.UNPAUSED_ACTION_WHITELIST

    @staticmethod
    def _stepwise_state_path(run_root: Path) -> Path:
        return run_root / "stepwise_session.json"

    def _save_stepwise_state(self, run_root: Path, state: dict[str, Any]) -> None:
        self._stepwise_state_path(run_root).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_stepwise_state(self, run_root: Path) -> dict[str, Any]:
        path = self._stepwise_state_path(run_root)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _append_stepwise_event(run_root: Path, event: dict[str, Any]) -> None:
        logs_dir = run_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        with (logs_dir / "driver_flow_events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def _write_stepwise_driver_flow(run_root: Path, step_results: list[dict[str, Any]]) -> None:
        (run_root / "logs" / "driver_flow.json").write_text(
            json.dumps({"steps": step_results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _write_stepwise_flow_report(run_root: Path, state: dict[str, Any]) -> None:
        out = {
            "flow_id": str(state.get("flow_id", "")),
            "flow_file": str(state.get("flow_file", "")),
            "status": str(state.get("status", "")),
            "started_at": str(state.get("started_at", "")),
            "finished_at": str(state.get("finished_at", "")),
            "run_id": str(state.get("run_id", "")),
            "driver_steps": state.get("driver_steps", []),
            "pid": int(state.get("pid", 0) or 0),
            "pid_exit_verified": bool(state.get("pid_exit_verified", False)),
            "last_error": str(state.get("last_error", "")),
        }
        (run_root / "flow_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _is_pid_running(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            try:
                probe = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=2,
                )
            except Exception:
                return True
            out = str(probe.stdout or "").strip()
            if not out:
                return False
            lowered = out.lower()
            if lowered.startswith("info:") or "no tasks are running" in lowered:
                return False
            return f'"{pid}"' in out
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def _terminate_pid(self, pid: int, wait_timeout_sec: float = 8.0) -> dict[str, Any]:
        result: dict[str, Any] = {
            "pid": int(pid),
            "attempted": False,
            "pid_exited": True,
            "method": "none",
        }
        if pid <= 0:
            return result
        result["attempted"] = True
        if not self._is_pid_running(pid):
            return result
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T"],
                capture_output=True,
                text=True,
                check=False,
            )
            result["method"] = "taskkill_soft"
        except Exception:
            pass
        soft_deadline = time.monotonic() + max(0.2, float(wait_timeout_sec) * 0.5)
        while time.monotonic() < soft_deadline:
            if not self._is_pid_running(pid):
                result["pid_exited"] = True
                return result
            time.sleep(0.05)
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
            result["method"] = "taskkill_force"
        except Exception:
            pass
        hard_deadline = time.monotonic() + max(0.2, float(wait_timeout_sec) * 0.5)
        while time.monotonic() < hard_deadline:
            if not self._is_pid_running(pid):
                result["pid_exited"] = True
                return result
            time.sleep(0.05)
        result["pid_exited"] = not self._is_pid_running(pid)
        return result

    @staticmethod
    def _chat_status_zh(status: str) -> str:
        s = str(status or "").strip().lower()
        return {
            "passed": "通过",
            "failed": "失败",
            "running": "进行中",
            "ready": "就绪",
            "ok": "成功",
        }.get(s, str(status or "未知").strip() or "未知")

    @staticmethod
    def _build_stepwise_chat_event(
        *,
        phase: str,
        step_id: str,
        action: str,
        step_index: int,
        step_total: int,
        status: str = "",
        detail: str = "",
        event_utc: str = "",
        game_time: str = "",
        requires_unpaused: bool | None = None,
        paused_by_plugin: bool | None = None,
        step_enter_runtime: dict[str, Any] | None = None,
        step_exit_runtime: dict[str, Any] | None = None,
        runtime_window: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        progress = f"{step_index + 1}/{step_total}" if step_total > 0 and step_index >= 0 else ""
        doing, goal = human_step_and_goal(step_id, action)
        goal_s = str(goal or "").strip()
        detail_s = str(detail or "").strip()
        if phase == "about_to_start":
            text = f"即将开始：{doing}"
        elif phase == "started":
            text = f"开始执行：{doing}"
        elif phase == "result":
            st_zh = StepwiseSupportMixin._chat_status_zh(status)
            text = f"执行结果：{doing}（{st_zh}）"
            if detail_s and str(status or "").strip().lower() == "failed":
                text = f"{text} · {detail_s}"
        elif phase == "verify":
            verdict = "通过" if str(status or "").strip().lower() == "passed" else "失败"
            text = f"验证结论：{verdict}"
            if verdict == "通过" and goal_s:
                text = f"{text} · {goal_s}"
            elif verdict == "失败" and detail_s:
                text = f"{text}（{detail_s}）"
        else:
            text = f"{doing}（{step_id} · {action}）" if (step_id or action) else doing
        event_ts = str(event_utc or datetime.now(timezone.utc).isoformat())
        out = {
            "phase": phase,
            "text": text,
            "step_id": step_id,
            "action": action,
            "progress": progress,
            "status": status,
            "detail": detail,
            "event_utc": event_ts,
            "game_time": str(game_time or ""),
            "ts": event_ts,
        }
        if requires_unpaused is not None:
            out["requires_unpaused"] = bool(requires_unpaused)
        if paused_by_plugin is not None:
            out["paused_by_plugin"] = bool(paused_by_plugin)
        if isinstance(step_enter_runtime, dict):
            out["step_enter_runtime"] = step_enter_runtime
        if isinstance(step_exit_runtime, dict):
            out["step_exit_runtime"] = step_exit_runtime
        if isinstance(runtime_window, dict):
            out["runtime_window"] = runtime_window
        return out

    def _finalize_stepwise_session(self, run_root: Path, state: dict[str, Any], final_status: str, error: str = "") -> None:
        normalized_final = "passed" if str(final_status).strip().lower() == "passed" else "failed"
        state["status"] = normalized_final
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        state["last_error"] = str(error or "").strip()
        pid = int(state.get("pid", 0) or 0)
        termination = self._terminate_pid(pid) if pid > 0 else {"pid": 0, "attempted": False, "pid_exited": True, "method": "none"}
        state["pid_exit_verified"] = bool(termination.get("pid_exited", False))
        state["pid_terminate_attempted"] = bool(termination.get("attempted", False))
        state["pid_terminate_method"] = str(termination.get("method", "none"))
        if bool(termination.get("pid_exited", False)):
            state["pid"] = 0
        if bool(state.get("runtime_lock_acquired", False)):
            project_root = Path(str(state.get("project_root", "")).strip())
            if str(project_root):
                release_runtime_lock(project_root, int(termination.get("pid", 0) or 0))
            state["runtime_lock_acquired"] = False
        self._write_stepwise_flow_report(run_root, state)
        report_payload: dict[str, Any] = {
            "runId": str(state.get("run_id", "")),
            "status": normalized_final,
            "resultStatus": normalized_final,
            "result_status": normalized_final,
            "effective_exit_code": 0 if normalized_final == "passed" else 1,
            "process_exit_code": 0 if normalized_final == "passed" else 1,
            "artifacts": {"root": to_posix(run_root)},
            "lifecycle": {
                "pid": int(termination.get("pid", 0) or 0),
                "pid_exit_verified": bool(termination.get("pid_exited", False)),
                "termination_attempted": bool(termination.get("attempted", False)),
                "termination_method": str(termination.get("method", "none")),
            },
            "failures": [],
        }
        if error and normalized_final != "passed":
            report_payload["failures"] = [
                {
                    "stepId": str(state.get("last_step_id", "")),
                    "category": "runtime_error",
                    "expected": "step verification passed",
                    "actual": error,
                    "artifacts": ["logs/driver_flow.json", "flow_report.json"],
                }
            ]
        (run_root / "report.json").write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        run_meta = {
            "run_id": str(state.get("run_id", "")),
            "status": normalized_final,
            "flow_status": normalized_final,
            "startedAt": str(state.get("started_at", "")),
            "finishedAt": str(state.get("finished_at", "")),
            "flowFile": str(state.get("flow_file", "")),
            "mode": "stepwise",
            "pid": int(termination.get("pid", 0) or 0),
            "pid_exit_verified": bool(termination.get("pid_exited", False)),
            "termination_attempted": bool(termination.get("attempted", False)),
            "termination_method": str(termination.get("method", "none")),
        }
        (run_root / "run_meta.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self._save_stepwise_state(run_root, state)
