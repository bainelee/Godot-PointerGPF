from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fix_loop_service import default_fix_loop_payload, normalize_bounded_auto_fix
from flow_path_resolver import resolve_flow_path
from flow_runner import execute_flow_file
from server_common import (
    first_failure_reason,
    load_report,
    primary_failure_summary,
    report_exit_codes,
    resolve_godot_bin,
    to_posix,
    with_status_shape,
)
from server_errors import AppError


class FixLoopHandlersMixin:
    def run_game_flow(self, arguments: dict[str, Any]) -> dict[str, Any]:
        flow_file_raw = str(arguments.get("flow_file", "")).strip()
        if not flow_file_raw:
            raise AppError("INVALID_ARGUMENT", "flow_file is required")
        project_root_raw = arguments.get("project_root", str(self.default_project_root))
        project_root = Path(str(project_root_raw)).resolve()
        flow_file = resolve_flow_path(project_root=project_root, raw_flow_file=flow_file_raw)
        if not flow_file.exists():
            raise AppError("NOT_FOUND", f"flow file not found: {flow_file}")
        timeout_sec = int(arguments.get("timeout_sec", 300))
        dry_run = bool(arguments.get("dry_run", False))
        driver_ready_timeout_sec = (
            int(arguments["driver_ready_timeout_sec"]) if arguments.get("driver_ready_timeout_sec") is not None else None
        )
        driver_no_activity_timeout_sec = (
            int(arguments["driver_no_activity_timeout_sec"])
            if arguments.get("driver_no_activity_timeout_sec") is not None
            else None
        )
        requested_godot_bin = str(arguments.get("godot_bin", "godot4"))
        godot_bin, godot_resolution = resolve_godot_bin(
            requested=requested_godot_bin,
            strict=bool(arguments.get("strict_godot_bin", False)),
            allow_unresolved=dry_run,
            project_root=project_root,
        )
        payload, code = execute_flow_file(
            flow_file=flow_file,
            project_root=project_root,
            godot_bin=godot_bin,
            timeout_sec=timeout_sec,
            dry_run=dry_run,
            driver_ready_timeout_sec=driver_ready_timeout_sec,
            driver_no_activity_timeout_sec=driver_no_activity_timeout_sec,
            run_id=str(arguments.get("run_id", "")).strip() or None,
            allow_parallel=bool(arguments.get("allow_parallel", False)),
        )
        payload["exit_code"] = code
        payload["flow_status"] = str(payload.get("status", ""))
        payload["godot_bin_requested"] = requested_godot_bin
        payload["godot_bin_resolved"] = godot_bin
        payload["godot_bin_resolution"] = godot_resolution
        initial_report = load_report(Path(payload["artifact_root"]))
        initial_effective_exit_code, initial_process_exit_code = report_exit_codes(initial_report)
        payload["effective_exit_code"] = initial_effective_exit_code
        payload["process_exit_code"] = initial_process_exit_code
        payload["primary_failure"] = primary_failure_summary(initial_report)
        payload["fix_loop"] = default_fix_loop_payload()
        bounded_auto_fix = normalize_bounded_auto_fix(
            arguments.get("bounded_auto_fix", arguments.get("bounded_auto_fix_max_rounds", 0))
        )
        if bounded_auto_fix <= 0:
            payload["status"] = "resolved" if code == 0 else "exhausted"
            payload["current_step"] = "completed"
            payload["fix_loop_round"] = 0
            payload["approval_required"] = False
            self._save_fix_loop_state(
                Path(payload["artifact_root"]),
                {
                    "version": 2,
                    "run_id": str(payload.get("run_id", "")),
                    "artifact_root": to_posix(Path(payload["artifact_root"])),
                    "status": payload["status"],
                    "current_step": payload["current_step"],
                    "fix_loop_round": 0,
                    "approval_required": False,
                    "fix_loop": payload["fix_loop"],
                },
            )
            return with_status_shape(payload)
        approve_fix = bool(arguments.get("approve_fix_plan", False))
        fix_rounds: list[dict[str, Any]] = []
        fix_loop = {
            "enabled": True,
            "max_rounds": bounded_auto_fix,
            "rounds_executed": 0,
            "approval_required": False,
            "status": "analyzing",
            "rounds": fix_rounds,
        }
        if code == 0:
            fix_loop["status"] = "resolved"
            payload["fix_loop"] = fix_loop
            payload["status"] = "resolved"
            payload["current_step"] = "resolved"
            payload["fix_loop_round"] = 0
            payload["approval_required"] = False
            self._save_fix_loop_state(
                Path(payload["artifact_root"]),
                {
                    "version": 2,
                    "run_id": str(payload.get("run_id", "")),
                    "artifact_root": to_posix(Path(payload["artifact_root"])),
                    "status": "resolved",
                    "current_step": "resolved",
                    "fix_loop_round": 0,
                    "approval_required": False,
                    "fix_loop": fix_loop,
                    "config": {
                        "flow_file": to_posix(flow_file),
                        "project_root": to_posix(project_root),
                        "godot_bin": godot_bin,
                        "godot_bin_requested": requested_godot_bin,
                        "godot_bin_resolution": godot_resolution,
                        "timeout_sec": timeout_sec,
                        "dry_run": dry_run,
                        "driver_ready_timeout_sec": driver_ready_timeout_sec,
                        "driver_no_activity_timeout_sec": driver_no_activity_timeout_sec,
                        "bounded_auto_fix": bounded_auto_fix,
                        "allow_parallel": bool(arguments.get("allow_parallel", False)),
                    },
                },
            )
            return with_status_shape(payload)
        initial_reason = first_failure_reason(initial_report)
        fix_loop["rounds"].append(
            {
                "round": 0,
                "run_id": payload.get("run_id", ""),
                "status": payload.get("status", "failed"),
                "reason": initial_reason,
                "primary_failure": primary_failure_summary(initial_report),
            }
        )
        fix_loop["rounds_executed"] = 0
        run_root = Path(payload["artifact_root"])
        state: dict[str, Any] = {
            "version": 2,
            "run_id": str(payload.get("run_id", "")),
            "artifact_root": to_posix(run_root),
            "status": "analyzing",
            "current_step": "analyzing",
            "fix_loop_round": 0,
            "approval_required": False,
            "fix_loop": fix_loop,
            "config": {
                "flow_file": to_posix(flow_file),
                "project_root": to_posix(project_root),
                "godot_bin": godot_bin,
                "godot_bin_requested": requested_godot_bin,
                "godot_bin_resolution": godot_resolution,
                "timeout_sec": timeout_sec,
                "dry_run": dry_run,
                "driver_ready_timeout_sec": driver_ready_timeout_sec,
                "driver_no_activity_timeout_sec": driver_no_activity_timeout_sec,
                "bounded_auto_fix": bounded_auto_fix,
                "allow_parallel": bool(arguments.get("allow_parallel", False)),
            },
            "last_payload": payload,
        }
        self._save_fix_loop_state(run_root, state)
        if not approve_fix:
            fix_loop["approval_required"] = True
            fix_loop["status"] = "waiting_approval"
            payload["fix_loop"] = fix_loop
            payload["status"] = "waiting_approval"
            payload["current_step"] = "waiting_approval"
            payload["fix_loop_round"] = 0
            payload["approval_required"] = True
            payload["proposed_fix_plan"] = {
                "summary": "Retry flow with bounded auto-fix rounds",
                "max_rounds": bounded_auto_fix,
                "first_failure_reason": initial_reason,
            }
            state["status"] = "waiting_approval"
            state["current_step"] = "waiting_approval"
            state["approval_required"] = True
            state["fix_loop_round"] = 0
            state["fix_loop"] = fix_loop
            state["last_payload"] = payload
            self._save_fix_loop_state(run_root, state)
            return with_status_shape(payload)
        return self._resume_fix_loop_impl(
            run_root=run_root,
            state=state,
            force=False,
        )

    def get_test_run_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        if not run_id:
            raise AppError("INVALID_ARGUMENT", "run_id is required")
        _, state = self._load_status_by_run_id(run_id, arguments)
        return with_status_shape(
            {
                "run_id": state.get("run_id", run_id),
                "artifact_root": state.get("artifact_root", ""),
                "status": state.get("status", ""),
                "current_step": state.get("current_step", ""),
                "fix_loop_round": int(state.get("fix_loop_round", 0)),
                "approval_required": bool(state.get("approval_required", False)),
                "fix_loop": state.get("fix_loop", {}),
            }
        )

    def cancel_test_run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        if not run_id:
            raise AppError("INVALID_ARGUMENT", "run_id is required")
        run_root, state = self._load_status_by_run_id(run_id, arguments)
        if state.get("status") in {"resolved", "exhausted"}:
            return with_status_shape(
                {
                    "run_id": state.get("run_id", run_id),
                    "artifact_root": state.get("artifact_root", ""),
                    "status": state.get("status", ""),
                    "current_step": state.get("current_step", ""),
                    "fix_loop_round": int(state.get("fix_loop_round", 0)),
                    "approval_required": bool(state.get("approval_required", False)),
                    "fix_loop": state.get("fix_loop", {}),
                    "cancelled": False,
                }
            )
        state["status"] = "cancelled"
        state["current_step"] = "cancelled"
        state["approval_required"] = False
        state["cancel_requested"] = True
        fix_loop = state.get("fix_loop", {})
        if isinstance(fix_loop, dict):
            fix_loop["status"] = "cancelled"
            fix_loop["approval_required"] = False
            state["fix_loop"] = fix_loop
        self._save_fix_loop_state(run_root, state)
        return with_status_shape(
            {
                "run_id": state.get("run_id", run_id),
                "artifact_root": state.get("artifact_root", ""),
                "status": state.get("status", ""),
                "current_step": state.get("current_step", ""),
                "fix_loop_round": int(state.get("fix_loop_round", 0)),
                "approval_required": bool(state.get("approval_required", False)),
                "fix_loop": state.get("fix_loop", {}),
                "cancelled": True,
            }
        )

    def resume_fix_loop(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        if not run_id:
            raise AppError("INVALID_ARGUMENT", "run_id is required")
        run_root, state = self._load_status_by_run_id(run_id, arguments)
        force = bool(arguments.get("force", False))
        return self._resume_fix_loop_impl(run_root=run_root, state=state, force=force)

    def _resume_fix_loop_impl(self, run_root: Path, state: dict[str, Any], force: bool) -> dict[str, Any]:
        status = str(state.get("status", ""))
        if status in {"resolved", "exhausted", "cancelled"}:
            return with_status_shape(
                {
                    "run_id": state.get("run_id", ""),
                    "artifact_root": state.get("artifact_root", ""),
                    "status": status,
                    "current_step": state.get("current_step", ""),
                    "fix_loop_round": int(state.get("fix_loop_round", 0)),
                    "approval_required": bool(state.get("approval_required", False)),
                    "fix_loop": state.get("fix_loop", {}),
                    "last_payload": state.get("last_payload", {}),
                }
            )
        if status != "waiting_approval" and not force:
            raise AppError(
                "INVALID_STATE",
                "resume_fix_loop expects waiting_approval status; set force=true to resume anyway",
            )
        config = state.get("config", {})
        if not isinstance(config, dict):
            raise AppError("INVALID_STATE", "missing flow run config")
        flow_file = Path(str(config.get("flow_file", ""))).resolve()
        project_root = Path(str(config.get("project_root", ""))).resolve()
        if not flow_file.exists():
            raise AppError("NOT_FOUND", f"flow file not found: {flow_file}")
        bounded_auto_fix = normalize_bounded_auto_fix(config.get("bounded_auto_fix", 0))
        if bounded_auto_fix <= 0:
            raise AppError("INVALID_STATE", "bounded_auto_fix is disabled for this run")
        fix_loop = state.get("fix_loop", {})
        if not isinstance(fix_loop, dict):
            fix_loop = {}
        rounds = fix_loop.get("rounds", [])
        if not isinstance(rounds, list):
            rounds = []
        executed = int(fix_loop.get("rounds_executed", 0))
        start_round = max(1, executed + 1)
        max_rounds = int(fix_loop.get("max_rounds", bounded_auto_fix))
        state["status"] = "rerun"
        state["current_step"] = "rerun"
        state["approval_required"] = False
        state["fix_loop"] = {
            "enabled": True,
            "max_rounds": max_rounds,
            "rounds_executed": executed,
            "approval_required": False,
            "status": "rerun",
            "rounds": rounds,
        }
        self._save_fix_loop_state(run_root, state)
        current_payload = state.get("last_payload", {})
        if not isinstance(current_payload, dict):
            current_payload = {}
        current_code = int(current_payload.get("exit_code", 1))
        previous_round_signature: Optional[tuple[str, str]] = None
        if rounds:
            last_pf = rounds[-1].get("primary_failure", {}) if isinstance(rounds[-1], dict) else {}
            if isinstance(last_pf, dict):
                previous_round_signature = (
                    str(last_pf.get("category", "")).strip(),
                    str(last_pf.get("actual", "")).strip(),
                )
        for round_idx in range(start_round, max_rounds + 1):
            latest_state = self._load_fix_loop_state(run_root)
            if str(latest_state.get("status", "")) == "cancelled":
                return with_status_shape(
                    {
                        "run_id": latest_state.get("run_id", ""),
                        "artifact_root": latest_state.get("artifact_root", ""),
                        "status": "cancelled",
                        "current_step": "cancelled",
                        "fix_loop_round": int(latest_state.get("fix_loop_round", round_idx - 1)),
                        "approval_required": False,
                        "fix_loop": latest_state.get("fix_loop", {}),
                    }
                )
            retry_payload, retry_code = execute_flow_file(
                flow_file=flow_file,
                project_root=project_root,
                godot_bin=str(config.get("godot_bin", "godot4")),
                timeout_sec=int(config.get("timeout_sec", 300)),
                dry_run=bool(config.get("dry_run", False)),
                driver_ready_timeout_sec=(
                    int(config["driver_ready_timeout_sec"]) if config.get("driver_ready_timeout_sec") is not None else None
                ),
                driver_no_activity_timeout_sec=(
                    int(config["driver_no_activity_timeout_sec"])
                    if config.get("driver_no_activity_timeout_sec") is not None
                    else None
                ),
                allow_parallel=bool(config.get("allow_parallel", False)),
            )
            retry_payload["exit_code"] = retry_code
            retry_payload["flow_status"] = str(retry_payload.get("status", ""))
            retry_payload["godot_bin_requested"] = str(config.get("godot_bin_requested", config.get("godot_bin", "")))
            retry_payload["godot_bin_resolved"] = str(config.get("godot_bin", ""))
            retry_payload["godot_bin_resolution"] = config.get("godot_bin_resolution", {})
            retry_report = load_report(Path(retry_payload["artifact_root"]))
            retry_effective_exit_code, retry_process_exit_code = report_exit_codes(retry_report)
            retry_payload["effective_exit_code"] = retry_effective_exit_code
            retry_payload["process_exit_code"] = retry_process_exit_code
            retry_reason = first_failure_reason(retry_report)
            retry_primary_failure = primary_failure_summary(retry_report)
            retry_payload["primary_failure"] = retry_primary_failure
            rounds.append(
                {
                    "round": round_idx,
                    "run_id": retry_payload.get("run_id", ""),
                    "status": retry_payload.get("status", "failed"),
                    "reason": retry_reason,
                    "primary_failure": retry_primary_failure,
                }
            )
            current_payload = retry_payload
            current_code = retry_code
            current_signature = (
                str(retry_primary_failure.get("category", "")).strip(),
                str(retry_primary_failure.get("actual", "")).strip(),
            )
            no_improvement = (
                retry_code != 0
                and round_idx >= 2
                and previous_round_signature is not None
                and previous_round_signature == current_signature
                and bool(current_signature[0])
            )
            previous_round_signature = current_signature
            fix_loop = state.get("fix_loop", {})
            if not isinstance(fix_loop, dict):
                fix_loop = {}
            fix_loop["enabled"] = True
            fix_loop["max_rounds"] = max_rounds
            fix_loop["rounds_executed"] = round_idx
            fix_loop["approval_required"] = False
            fix_loop["rounds"] = rounds
            fix_loop["status"] = "rerun"
            state["fix_loop"] = fix_loop
            state["last_payload"] = current_payload
            state["fix_loop_round"] = round_idx
            state["approval_required"] = False
            state["current_step"] = "rerun"
            state["status"] = "rerun"
            if retry_code == 0:
                fix_loop["status"] = "resolved"
                state["status"] = "resolved"
                state["current_step"] = "resolved"
                self._save_fix_loop_state(run_root, state)
                break
            if no_improvement:
                fix_loop["status"] = "exhausted"
                fix_loop["stop_reason"] = "same_failure_without_improvement_for_2_rounds"
                state["status"] = "exhausted"
                state["current_step"] = "exhausted"
                state["stop_reason"] = fix_loop["stop_reason"]
                self._save_fix_loop_state(run_root, state)
                break
            self._save_fix_loop_state(run_root, state)
        else:
            fix_loop = state.get("fix_loop", {})
            if isinstance(fix_loop, dict):
                fix_loop["status"] = "exhausted"
                state["fix_loop"] = fix_loop
            state["status"] = "exhausted"
            state["current_step"] = "exhausted"
            state["fix_loop_round"] = max_rounds
            self._save_fix_loop_state(run_root, state)
        final_status = str(state.get("status", "exhausted"))
        final_fix_loop = state.get("fix_loop", {})
        if isinstance(final_fix_loop, dict):
            final_fix_loop["rounds"] = rounds
        current_payload["fix_loop"] = final_fix_loop
        current_payload["exit_code"] = current_code
        current_payload["status"] = final_status
        current_payload["current_step"] = str(state.get("current_step", final_status))
        current_payload["fix_loop_round"] = int(state.get("fix_loop_round", len(rounds) - 1))
        current_payload["approval_required"] = False
        current_payload["artifact_root"] = str(state.get("artifact_root", to_posix(run_root)))
        current_payload["run_id"] = str(state.get("run_id", current_payload.get("run_id", "")))
        state["last_payload"] = current_payload
        self._save_fix_loop_state(run_root, state)
        return with_status_shape(current_payload)
