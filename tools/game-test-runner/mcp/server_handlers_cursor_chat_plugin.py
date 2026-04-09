from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from driver_client import DriverClient
from server_errors import AppError


class CursorChatPluginHandlersMixin:
    """Project-level Cursor chat plugin layer for chat-first stepwise relay."""
    CHAT_PROTOCOL_THREE_PHASE = "three_phase"
    CHAT_PROTOCOL_LEGACY = "legacy_five_phase"
    PAUSE_POLICY_STRICT = "strict"
    PAUSE_POLICY_LEGACY = "legacy"

    @staticmethod
    def _plugin_state_path(run_root: Path) -> Path:
        return run_root / "cursor_chat_plugin_state.json"

    def _load_plugin_state(self, run_root: Path) -> dict[str, Any]:
        p = self._plugin_state_path(run_root)
        if not p.exists():
            return {}
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return obj if isinstance(obj, dict) else {}

    def _save_plugin_state(self, run_root: Path, state: dict[str, Any]) -> None:
        self._plugin_state_path(run_root).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _append_plugin_events(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
        queue = state.get("queue", [])
        if not isinstance(queue, list):
            queue = []
        next_seq = int(state.get("next_event_seq", 1) or 1)
        for event in events:
            if not isinstance(event, dict):
                continue
            wrapped = dict(event)
            wrapped["seq"] = next_seq
            queue.append(wrapped)
            next_seq += 1
        state["queue"] = queue
        state["next_event_seq"] = next_seq

    @staticmethod
    def _normalize_plugin_queue(state: dict[str, Any]) -> None:
        queue = state.get("queue", [])
        if not isinstance(queue, list):
            state["queue"] = []
            state["next_event_seq"] = int(state.get("next_event_seq", 1) or 1)
            return
        normalized: list[dict[str, Any]] = []
        next_seq = int(state.get("next_event_seq", 1) or 1)
        max_seen_seq = 0
        for event in queue:
            if not isinstance(event, dict):
                continue
            wrapped = dict(event)
            seq = int(wrapped.get("seq", 0) or 0)
            if seq <= 0:
                seq = next_seq
                wrapped["seq"] = seq
                next_seq += 1
            max_seen_seq = max(max_seen_seq, seq)
            normalized.append(wrapped)
        state["queue"] = normalized
        if max_seen_seq <= 0:
            state["next_event_seq"] = next_seq
        else:
            state["next_event_seq"] = max(max_seen_seq + 1, next_seq)

    def _plugin_set_game_speed(self, run_root: Path, speed: float) -> bool:
        stepwise_state = self._load_stepwise_state(run_root)
        if not isinstance(stepwise_state, dict):
            return False
        driver_dir = Path(str(stepwise_state.get("driver_dir", "")).strip())
        if not str(driver_dir):
            return False
        try:
            client = DriverClient(base_dir=driver_dir)
            resp = client.send_and_wait(action="setGameTimeSpeed", params={"speed": float(speed)}, timeout_sec=5.0)
            return str(resp.get("status", "")) == "ok"
        except Exception:
            return False

    def _plugin_set_global_pause(self, run_root: Path, paused: bool) -> bool:
        stepwise_state = self._load_stepwise_state(run_root)
        if not isinstance(stepwise_state, dict):
            return False
        driver_dir = Path(str(stepwise_state.get("driver_dir", "")).strip())
        if not str(driver_dir):
            return False
        try:
            client = DriverClient(base_dir=driver_dir)
            resp = client.send_and_wait(action="setGlobalPause", params={"paused": bool(paused)}, timeout_sec=5.0)
            return str(resp.get("status", "")) == "ok"
        except Exception:
            return False

    @staticmethod
    def _runtime_hours(snapshot: dict[str, Any]) -> float | None:
        if not isinstance(snapshot, dict):
            return None
        value = snapshot.get("game_total_hours")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @staticmethod
    def _runtime_settled_hours(snapshot: dict[str, Any]) -> float | None:
        if not isinstance(snapshot, dict):
            return None
        clock = snapshot.get("settlement_clock")
        if isinstance(clock, dict):
            value = clock.get("settled_hours")
            if isinstance(value, (int, float)):
                return float(value)
        return None

    @staticmethod
    def _is_highrisk_step(step: dict[str, Any]) -> bool:
        if not isinstance(step, dict):
            return False
        action = str(step.get("action", "")).strip().lower()
        step_id = str(step.get("id", "")).strip().lower()
        if action in {"savegame", "check", "screenshot"}:
            return True
        return any(token in step_id for token in ("save", "continue", "screenshot", "verify"))

    def _plugin_capture_runtime_snapshot(self, run_root: Path) -> dict[str, Any]:
        stepwise_state = self._load_stepwise_state(run_root)
        if not isinstance(stepwise_state, dict):
            return {}
        driver_dir = Path(str(stepwise_state.get("driver_dir", "")).strip())
        if not str(driver_dir):
            return {}
        try:
            client = DriverClient(base_dir=driver_dir)
            resp = client.send_and_wait(
                action="getState",
                params={
                    "keys": [
                        "resources",
                        "game_total_hours",
                        "settlement_clock",
                        "resource_ledger",
                        "tree_paused",
                        "game_speed_multiplier",
                    ]
                },
                timeout_sec=5.0,
            )
            if str(resp.get("status", "")) != "ok":
                return {}
            data = resp.get("data", {})
            if not isinstance(data, dict):
                return {}
            data["snapshot_utc"] = datetime.now(timezone.utc).isoformat()
            return data
        except Exception:
            return {}

    @classmethod
    def _build_runtime_window(cls, enter: dict[str, Any], exit_snapshot: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        enter_hours = cls._runtime_hours(enter)
        exit_hours = cls._runtime_hours(exit_snapshot)
        if enter_hours is not None and exit_hours is not None:
            observed = float(exit_hours) - float(enter_hours)
            out["observed_game_hours"] = observed
        enter_settled = cls._runtime_settled_hours(enter)
        exit_settled = cls._runtime_settled_hours(exit_snapshot)
        if enter_settled is not None and exit_settled is not None:
            settled = float(exit_settled) - float(enter_settled)
            out["settled_game_hours"] = settled
            if "observed_game_hours" in out:
                out["ignored_runtime_hours"] = settled - float(out.get("observed_game_hours", 0.0))
        return out

    @staticmethod
    def _attach_runtime_to_events(
        events: list[dict[str, Any]],
        *,
        enter_runtime: dict[str, Any] | None,
        exit_runtime: dict[str, Any] | None,
        runtime_window: dict[str, Any] | None,
        auto_snapshot_highrisk: bool,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            wrapped = dict(event)
            if isinstance(enter_runtime, dict) and enter_runtime:
                wrapped["step_enter_runtime"] = enter_runtime
            if isinstance(exit_runtime, dict) and exit_runtime:
                wrapped["step_exit_runtime"] = exit_runtime
            if isinstance(runtime_window, dict) and runtime_window:
                wrapped["runtime_window"] = runtime_window
            if auto_snapshot_highrisk:
                wrapped["auto_snapshot_highrisk"] = True
            out.append(wrapped)
        return out

    def _plugin_pause_now(self, run_root: Path, state: dict[str, Any]) -> bool:
        ok = self._plugin_set_global_pause(run_root, paused=True)
        if ok:
            state["paused_by_plugin"] = True
        return ok

    def _plugin_resume_for_step(self, run_root: Path, state: dict[str, Any], requires_unpaused: bool) -> bool:
        if not requires_unpaused:
            return self._plugin_pause_now(run_root, state)
        resume_speed = float(state.get("resume_speed", 1.0) or 1.0)
        unpaused = self._plugin_set_global_pause(run_root, paused=False)
        speed_ok = self._plugin_set_game_speed(run_root, speed=resume_speed)
        if unpaused and speed_ok:
            state["paused_by_plugin"] = False
            return True
        return False

    @staticmethod
    def _tag_plugin_events(
        events: list[dict[str, Any]],
        *,
        requires_unpaused: bool,
        paused_by_plugin: bool,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            wrapped = dict(event)
            wrapped["requires_unpaused"] = bool(requires_unpaused)
            wrapped["paused_by_plugin"] = bool(paused_by_plugin)
            out.append(wrapped)
        return out

    def start_cursor_chat_plugin(self, arguments: dict[str, Any]) -> dict[str, Any]:
        started = self.start_stepwise_flow(arguments)
        run_id = str(started.get("run_id", "")).strip()
        if not run_id:
            raise AppError("INVALID_STATE", "start_stepwise_flow returned empty run_id")
        run_root = self._resolve_run_root(run_id, {"run_id": run_id})
        state = {
            "version": 1,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            # Cursor chat plugin sessions are always relay-locked by design.
            "relay_required": True,
            "relay_policy": "session_locked",
            "finished": False,
            "phase_state": "need_prepare",
            "active_step": {},
            "active_step_index": -1,
            "active_step_total": 0,
            "active_step_requires_unpaused": False,
            "active_step_enter_runtime": {},
            "active_step_exit_runtime": {},
            "queue": [],
            "emitted": 0,
            "next_event_seq": 1,
            "last_acked_seq": 0,
            "pause_during_think": bool(arguments.get("pause_during_think", True)),
            "paused_by_plugin": False,
            "resume_speed": float(arguments.get("resume_speed", 1.0) or 1.0),
            "chat_protocol_mode": str(arguments.get("chat_protocol_mode", self.CHAT_PROTOCOL_THREE_PHASE)).strip()
            or self.CHAT_PROTOCOL_THREE_PHASE,
            "pause_policy": str(arguments.get("pause_policy", self.PAUSE_POLICY_STRICT)).strip() or self.PAUSE_POLICY_STRICT,
        }
        if str(state["chat_protocol_mode"]) not in {self.CHAT_PROTOCOL_THREE_PHASE, self.CHAT_PROTOCOL_LEGACY}:
            state["chat_protocol_mode"] = self.CHAT_PROTOCOL_THREE_PHASE
        if str(state["pause_policy"]) not in {self.PAUSE_POLICY_STRICT, self.PAUSE_POLICY_LEGACY}:
            state["pause_policy"] = self.PAUSE_POLICY_STRICT
        should_pause_boot = str(state.get("pause_policy", "")) == self.PAUSE_POLICY_STRICT or bool(
            state["pause_during_think"]
        )
        if should_pause_boot:
            self._plugin_pause_now(run_root, state)
        self._save_plugin_state(run_root, state)
        relay_forced = not bool(arguments.get("chat_relay_required", True))
        return {
            "run_id": run_id,
            "status": "running",
            "mode": "cursor_chat_plugin",
            "relay_required": True,
            "relay_policy": "session_locked",
            "relay_forced": relay_forced,
            "total_steps": int(started.get("total_steps", 0)),
            "next_step": started.get("next_step", {}),
            "artifact_root": started.get("artifact_root", ""),
            "pause_during_think": bool(state.get("pause_during_think", False)),
            "chat_protocol_mode": str(state.get("chat_protocol_mode", self.CHAT_PROTOCOL_THREE_PHASE)),
            "pause_policy": str(state.get("pause_policy", self.PAUSE_POLICY_STRICT)),
        }

    @staticmethod
    def _build_plugin_stage5_event(verify: dict[str, Any], active_step: dict[str, Any], game_time: str = "") -> dict[str, Any]:
        verified = bool(verify.get("verified", False))
        status = str(verify.get("status", "running"))
        step_id = str(active_step.get("id", ""))
        action = str(active_step.get("action", ""))
        step_total = int(verify.get("step_total", 0))
        step_index = int(verify.get("step_index", -1))
        progress = f"{step_index + 1}/{step_total}" if step_total > 0 and step_index >= 0 else ""
        if verified and status != "finished":
            next_step = verify.get("next_step", {}) if isinstance(verify.get("next_step"), dict) else {}
            text = f"通过验证进入下一步：{str(next_step.get('id', '')).strip() or 'next'}"
            st = "passed"
        elif verified and status == "finished":
            text = "通过验证，流程结束"
            st = "passed"
        else:
            text = "验证失败，立即停止"
            st = "failed"
        event_utc = datetime.now(timezone.utc).isoformat()
        return {
            "phase": "next",
            "text": text,
            "step_id": step_id,
            "action": action,
            "progress": progress,
            "status": st,
            "detail": "",
            "event_utc": event_utc,
            "game_time": str(game_time or ""),
            "ts": event_utc,
        }

    def pull_cursor_chat_plugin(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        if not run_id:
            raise AppError("INVALID_ARGUMENT", "run_id is required")
        max_batch = int(arguments.get("max_batch", 1))
        if max_batch <= 0:
            raise AppError("INVALID_ARGUMENT", "max_batch must be >= 1")
        max_batch = min(max_batch, 20)
        run_root = self._resolve_run_root(run_id, arguments)
        state = self._load_plugin_state(run_root)
        if not state:
            raise AppError("NOT_FOUND", f"cursor chat plugin state missing for run_id: {run_id}")
        queue = state.get("queue", [])
        if not isinstance(queue, list):
            queue = []
        self._normalize_plugin_queue(state)
        queue = state.get("queue", [])
        has_ack_seq = "ack_seq" in arguments
        ack_seq = int(arguments.get("ack_seq", 0) or 0)
        if has_ack_seq and ack_seq > 0:
            queue = [e for e in queue if isinstance(e, dict) and int(e.get("seq", 0) or 0) > ack_seq]
            state["queue"] = queue
            state["last_acked_seq"] = max(int(state.get("last_acked_seq", 0) or 0), ack_seq)

        if (not queue) and (not bool(state.get("finished", False))):
            phase_state = str(state.get("phase_state", "need_prepare"))
            active_step = state.get("active_step", {})
            if not isinstance(active_step, dict):
                active_step = {}
            chat_protocol_mode = str(state.get("chat_protocol_mode", self.CHAT_PROTOCOL_THREE_PHASE)).strip()
            if chat_protocol_mode not in {self.CHAT_PROTOCOL_THREE_PHASE, self.CHAT_PROTOCOL_LEGACY}:
                chat_protocol_mode = self.CHAT_PROTOCOL_THREE_PHASE
                state["chat_protocol_mode"] = chat_protocol_mode
            pause_policy = str(state.get("pause_policy", self.PAUSE_POLICY_STRICT)).strip()
            if pause_policy not in {self.PAUSE_POLICY_STRICT, self.PAUSE_POLICY_LEGACY}:
                pause_policy = self.PAUSE_POLICY_STRICT
                state["pause_policy"] = pause_policy

            if phase_state == "need_prepare":
                prepare = self.prepare_step({"run_id": run_id})
                if str(prepare.get("status", "")) == "finished":
                    state["finished"] = True
                    state["phase_state"] = "done"
                else:
                    step = prepare.get("step", {}) if isinstance(prepare.get("step"), dict) else {}
                    state["active_step"] = step
                    state["active_step_index"] = int(prepare.get("step_index", -1))
                    state["active_step_total"] = int(prepare.get("step_total", 0))
                    state["active_step_requires_unpaused"] = bool(self._step_requires_unpaused(step))
                    if chat_protocol_mode == self.CHAT_PROTOCOL_LEGACY:
                        about_events = [
                            e
                            for e in (prepare.get("chat_events", []) if isinstance(prepare.get("chat_events"), list) else [])
                            if isinstance(e, dict) and str(e.get("phase", "")) == "about_to_start"
                        ]
                        if not about_events:
                            about_events = [
                                self._build_stepwise_chat_event(
                                    phase="about_to_start",
                                    step_id=str(step.get("id", "")),
                                    action=str(step.get("action", "")),
                                    step_index=int(state.get("active_step_index", -1)),
                                    step_total=int(state.get("active_step_total", 0)),
                                    status="running",
                                )
                            ]
                        self._append_plugin_events(
                            state,
                            self._tag_plugin_events(
                                about_events,
                                requires_unpaused=bool(state.get("active_step_requires_unpaused", False)),
                                paused_by_plugin=bool(state.get("paused_by_plugin", False)),
                            ),
                        )
                        queue = state.get("queue", [])
                    state["phase_state"] = "need_started"

            elif phase_state == "need_started":
                step_id = str(active_step.get("id", ""))
                action = str(active_step.get("action", ""))
                enter_runtime = self._plugin_capture_runtime_snapshot(run_root)
                state["active_step_enter_runtime"] = enter_runtime
                started_event = self._build_stepwise_chat_event(
                    phase="started",
                    step_id=step_id,
                    action=action,
                    step_index=int(state.get("active_step_index", -1)),
                    step_total=int(state.get("active_step_total", 0)),
                    status="running",
                    step_enter_runtime=enter_runtime if isinstance(enter_runtime, dict) and enter_runtime else None,
                )
                self._append_plugin_events(
                    state,
                    self._tag_plugin_events(
                        [started_event],
                        requires_unpaused=bool(state.get("active_step_requires_unpaused", False)),
                        paused_by_plugin=bool(state.get("paused_by_plugin", False)),
                    ),
                )
                queue = state.get("queue", [])
                state["phase_state"] = "need_execute"

            elif phase_state == "need_execute":
                requires_unpaused = bool(state.get("active_step_requires_unpaused", False))
                auto_snapshot_highrisk = self._is_highrisk_step(active_step)
                if pause_policy == self.PAUSE_POLICY_STRICT:
                    self._plugin_resume_for_step(run_root, state, requires_unpaused=requires_unpaused)
                elif bool(state.get("pause_during_think", False)) and bool(state.get("paused_by_plugin", False)):
                    self._plugin_resume_for_step(run_root, state, requires_unpaused=True)
                execute = self.execute_step({"run_id": run_id})
                result_events = [
                    e
                    for e in (execute.get("chat_events", []) if isinstance(execute.get("chat_events"), list) else [])
                    if isinstance(e, dict) and str(e.get("phase", "")) == "result"
                ]
                if not result_events:
                    result_events = [
                        self._build_stepwise_chat_event(
                            phase="result",
                            step_id=str(active_step.get("id", "")),
                            action=str(active_step.get("action", "")),
                            step_index=int(state.get("active_step_index", -1)),
                            step_total=int(state.get("active_step_total", 0)),
                            status="running",
                            detail="执行完成",
                            game_time=str(execute.get("game_time", "")),
                            step_enter_runtime=(
                                state.get("active_step_enter_runtime")
                                if isinstance(state.get("active_step_enter_runtime"), dict)
                                else None
                            ),
                        )
                    ]
                if str(active_step.get("action", "")) == "setGameTimeSpeed":
                    params = active_step.get("params", {})
                    if isinstance(params, dict):
                        speed = float(params.get("speed", 0.0) or 0.0)
                        if speed > 0:
                            state["resume_speed"] = speed
                if pause_policy == self.PAUSE_POLICY_STRICT or bool(state.get("pause_during_think", False)):
                    self._plugin_pause_now(run_root, state)
                exit_runtime = self._plugin_capture_runtime_snapshot(run_root)
                state["active_step_exit_runtime"] = exit_runtime
                runtime_window = self._build_runtime_window(
                    state.get("active_step_enter_runtime")
                    if isinstance(state.get("active_step_enter_runtime"), dict)
                    else {},
                    exit_runtime if isinstance(exit_runtime, dict) else {},
                )
                result_events = self._attach_runtime_to_events(
                    result_events,
                    enter_runtime=state.get("active_step_enter_runtime")
                    if isinstance(state.get("active_step_enter_runtime"), dict)
                    else None,
                    exit_runtime=exit_runtime if isinstance(exit_runtime, dict) else None,
                    runtime_window=runtime_window if isinstance(runtime_window, dict) else None,
                    auto_snapshot_highrisk=auto_snapshot_highrisk,
                )
                self._append_plugin_events(
                    state,
                    self._tag_plugin_events(
                        result_events,
                        requires_unpaused=requires_unpaused,
                        paused_by_plugin=bool(state.get("paused_by_plugin", False)),
                    ),
                )
                queue = state.get("queue", [])
                state["phase_state"] = "need_verify"

            elif phase_state == "need_verify":
                verify = self.verify_step({"run_id": run_id})
                verify_events = [
                    e
                    for e in (verify.get("chat_events", []) if isinstance(verify.get("chat_events"), list) else [])
                    if isinstance(e, dict) and str(e.get("phase", "")) == "verify"
                ]
                if pause_policy == self.PAUSE_POLICY_STRICT or bool(state.get("pause_during_think", False)):
                    self._plugin_pause_now(run_root, state)
                verify_events = self._attach_runtime_to_events(
                    verify_events,
                    enter_runtime=state.get("active_step_enter_runtime")
                    if isinstance(state.get("active_step_enter_runtime"), dict)
                    else None,
                    exit_runtime=state.get("active_step_exit_runtime")
                    if isinstance(state.get("active_step_exit_runtime"), dict)
                    else None,
                    runtime_window=self._build_runtime_window(
                        state.get("active_step_enter_runtime")
                        if isinstance(state.get("active_step_enter_runtime"), dict)
                        else {},
                        state.get("active_step_exit_runtime")
                        if isinstance(state.get("active_step_exit_runtime"), dict)
                        else {},
                    ),
                    auto_snapshot_highrisk=self._is_highrisk_step(active_step),
                )
                self._append_plugin_events(
                    state,
                    self._tag_plugin_events(
                        verify_events,
                        requires_unpaused=bool(state.get("active_step_requires_unpaused", False)),
                        paused_by_plugin=bool(state.get("paused_by_plugin", False)),
                    ),
                )
                queue = state.get("queue", [])
                if chat_protocol_mode == self.CHAT_PROTOCOL_LEGACY:
                    game_time = str(verify_events[0].get("game_time", "")) if verify_events else ""
                    self._append_plugin_events(
                        state,
                        self._tag_plugin_events(
                            [self._build_plugin_stage5_event(verify=verify, active_step=active_step, game_time=game_time)],
                            requires_unpaused=bool(state.get("active_step_requires_unpaused", False)),
                            paused_by_plugin=bool(state.get("paused_by_plugin", False)),
                        ),
                    )
                    queue = state.get("queue", [])
                if str(verify.get("status", "")) == "finished":
                    state["finished"] = True
                    state["phase_state"] = "done"
                    state["active_step"] = {}
                    state["active_step_requires_unpaused"] = False
                    state["active_step_enter_runtime"] = {}
                    state["active_step_exit_runtime"] = {}
                else:
                    state["phase_state"] = "need_prepare"
                    state["active_step"] = {}
                    state["active_step_index"] = -1
                    state["active_step_total"] = 0
                    state["active_step_requires_unpaused"] = False
                    state["active_step_enter_runtime"] = {}
                    state["active_step_exit_runtime"] = {}

            self._save_plugin_state(run_root, state)

        if not queue:
            self._save_plugin_state(run_root, state)
            return {
                "run_id": run_id,
                "event": {},
                "events": [],
                "remaining": 0,
                "finished": bool(state.get("finished", False)),
                "emitted": int(state.get("emitted", 0)),
                "max_batch": max_batch,
                "paused_by_plugin": bool(state.get("paused_by_plugin", False)),
            }

        events: list[dict[str, Any]] = []
        take = min(max_batch, len(queue))
        if has_ack_seq:
            for idx in range(take):
                event = queue[idx]
                if isinstance(event, dict):
                    events.append(event)
        else:
            for _ in range(take):
                event = queue.pop(0)
                if isinstance(event, dict):
                    events.append(event)
            state["queue"] = queue
        state["emitted"] = int(state.get("emitted", 0)) + len(events)
        self._save_plugin_state(run_root, state)
        return {
            "run_id": run_id,
            "event": events[0] if events else {},
            "events": events,
            "remaining": len(queue),
            "finished": bool(state.get("finished", False)) and len(queue) == 0,
            "emitted": int(state.get("emitted", 0)),
            "max_batch": max_batch,
            "paused_by_plugin": bool(state.get("paused_by_plugin", False)),
            "last_acked_seq": int(state.get("last_acked_seq", 0)),
        }
