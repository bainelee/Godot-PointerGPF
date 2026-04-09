from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server_errors import AppError


class StepwiseAutopilotHandlersMixin:
    """Server-side stepwise autopilot to reduce round-trip latency."""

    def run_stepwise_autopilot(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        if not run_id:
            flow_file = str(arguments.get("flow_file", "")).strip()
            if not flow_file:
                raise AppError("INVALID_ARGUMENT", "run_id or flow_file is required")
            start_args = {
                "project_root": str(arguments.get("project_root", str(self.default_project_root))),
                "flow_file": flow_file,
                "godot_bin": str(arguments.get("godot_bin", "godot4")),
                "timeout_sec": int(arguments.get("timeout_sec", 300)),
            }
            if str(arguments.get("run_id_seed", "")).strip():
                start_args["run_id"] = str(arguments.get("run_id_seed", "")).strip()
            started = self.start_stepwise_flow(start_args)
            run_id = str(started.get("run_id", "")).strip()

        step_limit = int(arguments.get("step_limit", 0))
        stage_limit = int(arguments.get("stage_limit", 0))
        finalize_on_limit = bool(arguments.get("finalize_on_limit", False))
        stage_events: list[dict[str, Any]] = []
        step_summaries: list[dict[str, Any]] = []
        final_status = "running"
        flow_status = "running"
        steps_executed = 0
        capped_by = ""

        while True:
            once = self.step_once({"run_id": run_id})
            steps_executed += 1
            once_stage_events = once.get("stage_events", [])
            if isinstance(once_stage_events, list):
                stage_events.extend(once_stage_events)
            verified = bool(once.get("verified", False))
            current_status = str(once.get("status", "running"))
            current_flow_status = str(once.get("flow_status", "running"))
            step_summary = {
                "step_index": int(once.get("step_index", -1)),
                "step_total": int(once.get("step_total", 0)),
                "step_id": str((once.get("step", {}) or {}).get("id", "")),
                "action": str((once.get("step", {}) or {}).get("action", "")),
                "execution_status": str(once.get("execution_status", "")),
                "verified": verified,
                "status": current_status,
                "flow_status": current_flow_status,
                "verify_reason": str(once.get("verify_reason", "")),
                "latency_ms": int(once.get("latency_ms", 0)),
            }
            step_summaries.append(step_summary)

            stage5 = self._build_stage5_event(
                step_summary=step_summary,
                next_step=once.get("next_step", {}),
                game_time=str(once.get("game_time", "")),
            )
            stage_events.append(stage5)

            final_status = current_status
            flow_status = current_flow_status

            if stage_limit > 0 and len(stage_events) >= stage_limit:
                stage_events = stage_events[:stage_limit]
                capped_by = "stage_limit"
                break
            if step_limit > 0 and steps_executed >= step_limit:
                capped_by = "step_limit"
                break
            if current_status == "finished":
                break

        if capped_by and final_status != "finished" and finalize_on_limit:
            try:
                run_root = self._resolve_run_root(run_id, arguments)
                state = self._load_stepwise_state(run_root)
                if isinstance(state, dict) and str(state.get("status", "")) == "running":
                    self._finalize_stepwise_session(
                        run_root,
                        state,
                        final_status="failed",
                        error=f"autopilot early exit by {capped_by}",
                    )
                    final_status = "finished"
                    flow_status = "failed"
            except Exception:
                pass

        pid_exit_verified = False
        termination_method = ""
        try:
            run_root = self._resolve_run_root(run_id, arguments)
            state = self._load_stepwise_state(run_root)
            if isinstance(state, dict):
                pid_exit_verified = bool(state.get("pid_exit_verified", False))
                termination_method = str(state.get("pid_terminate_method", ""))
        except Exception:
            pass

        return {
            "run_id": run_id,
            "status": final_status,
            "flow_status": flow_status,
            "steps_executed": steps_executed,
            "capped_by": capped_by,
            "finalize_on_limit": finalize_on_limit,
            "stage_events": stage_events,
            "step_summaries": step_summaries,
            "pid_exit_verified": pid_exit_verified,
            "termination_method": termination_method,
        }

    @staticmethod
    def _build_stage5_event(step_summary: dict[str, Any], next_step: Any, game_time: str = "") -> dict[str, Any]:
        verified = bool(step_summary.get("verified", False))
        status = str(step_summary.get("status", "running"))
        step_total = int(step_summary.get("step_total", 0))
        step_index = int(step_summary.get("step_index", -1))
        progress = f"{step_index + 1}/{step_total}" if step_total > 0 and step_index >= 0 else ""
        if verified and status != "finished":
            next_step_id = str((next_step or {}).get("id", "")).strip() if isinstance(next_step, dict) else ""
            text = f"通过验证进入下一步：{next_step_id or 'next'}"
            stage = "next_step"
            stage_status = "passed"
        elif verified and status == "finished":
            text = "通过验证，流程结束"
            stage = "flow_finished"
            stage_status = "passed"
        else:
            text = "验证失败，立即停止"
            stage = "stopped"
            stage_status = "failed"
        event_utc = datetime.now(timezone.utc).isoformat()
        return {
            "phase": "next",
            "stage": stage,
            "text": text,
            "progress": progress,
            "status": stage_status,
            "step_id": str(step_summary.get("step_id", "")),
            "action": str(step_summary.get("action", "")),
            "event_utc": event_utc,
            "game_time": str(game_time or ""),
            "ts": event_utc,
        }
