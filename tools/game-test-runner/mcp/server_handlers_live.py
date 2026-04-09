from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from flow_live_service import build_live_start_payload, build_stream_entry, resolve_live_state
from flow_path_resolver import resolve_flow_path
from server_common import load_report, resolve_godot_bin, to_posix, live_run_id
from server_errors import AppError
from artifact_service import load_flow_report
from flow_timeline_reader import read_flow_timeline_payload


class LiveHandlersMixin:
    default_project_root: Path
    core_dir: Path

    def start_game_flow_live(self, arguments: dict[str, Any]) -> dict[str, Any]:
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
        requested_godot_bin = str(arguments.get("godot_bin", "godot4"))
        godot_bin, godot_resolution = resolve_godot_bin(
            requested=requested_godot_bin,
            strict=bool(arguments.get("strict_godot_bin", False)),
            allow_unresolved=dry_run,
            project_root=project_root,
        )
        run_id = str(arguments.get("run_id", "")).strip() or live_run_id(flow_file.stem)
        artifact_base = project_root / "artifacts" / "test-runs"
        run_root = artifact_base / run_id
        logs_dir = run_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = logs_dir / "live_flow_stdout.log"
        stderr_path = logs_dir / "live_flow_stderr.log"
        flow_runner_file = self.core_dir / "flow_runner.py"
        cmd = [
            sys.executable,
            str(flow_runner_file),
            "--flow-file",
            str(flow_file),
            "--project-root",
            str(project_root),
            "--godot-bin",
            str(godot_bin),
            "--timeout-sec",
            str(timeout_sec),
            "--run-id",
            run_id,
        ]
        if dry_run:
            cmd.append("--dry-run")
        if bool(arguments.get("allow_parallel", False)):
            cmd.append("--allow-parallel")
        with open(stdout_path, "w", encoding="utf-8") as out_fh, open(stderr_path, "w", encoding="utf-8") as err_fh:
            proc = subprocess.Popen(  # pylint: disable=consider-using-with
                cmd,
                cwd=str(project_root),
                stdout=out_fh,
                stderr=err_fh,
                text=True,
            )
        return build_live_start_payload(
            run_id=run_id,
            flow_file=flow_file,
            run_root=run_root,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            requested_godot_bin=requested_godot_bin,
            resolved_godot_bin=godot_bin,
            godot_bin_resolution=godot_resolution,
            pid=int(proc.pid),
            to_posix=to_posix,
        )

    def get_live_flow_progress(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        if not run_id:
            raise AppError("INVALID_ARGUMENT", "run_id is required")
        view = str(arguments.get("view", "chat")).strip().lower() or "chat"
        if view not in {"full", "chat"}:
            raise AppError("INVALID_ARGUMENT", "view must be full or chat")
        recent_steps_limit = int(arguments.get("recent_steps_limit", 3))
        chat_mode = str(arguments.get("chat_mode", "normal")).strip().lower() or "normal"
        if chat_mode not in {"normal", "short"}:
            raise AppError("INVALID_ARGUMENT", "chat_mode must be normal or short")
        event_since = int(arguments.get("event_since", -1))
        event_limit = int(arguments.get("event_limit", 1))
        if event_limit <= 0:
            raise AppError("INVALID_ARGUMENT", "event_limit must be > 0")
        artifact_base_raw = arguments.get("artifact_base")
        artifact_base = (
            Path(str(artifact_base_raw)).resolve()
            if artifact_base_raw
            else self.default_project_root / "artifacts" / "test-runs"
        )
        run_root = artifact_base / run_id
        if not run_root.exists():
            return {"run_id": run_id, "state": "pending", "message": "run directory not created yet"}
        report = load_report(run_root)
        flow_report = load_flow_report(run_root)
        timeline = read_flow_timeline_payload(
            run_id=run_id,
            run_root=run_root,
            report=report if isinstance(report, dict) else {},
            flow_report=flow_report if isinstance(flow_report, dict) else {},
            to_posix=to_posix,
            view=view,
            recent_steps_limit=recent_steps_limit,
            chat_mode=chat_mode,
            event_since=event_since,
            event_limit=event_limit,
        )
        state = resolve_live_state(run_root)
        timeline["state"] = state
        timeline["run_meta_json"] = "run_meta.json" if (run_root / "run_meta.json").exists() else ""
        timeline["driver_flow_json"] = "logs/driver_flow.json" if (run_root / "logs" / "driver_flow.json").exists() else ""
        return timeline

    def run_and_stream_flow(self, arguments: dict[str, Any]) -> dict[str, Any]:
        poll_interval_sec = float(arguments.get("poll_interval_sec", 1.0))
        max_wait_sec = int(arguments.get("max_wait_sec", 600))
        if poll_interval_sec <= 0:
            raise AppError("INVALID_ARGUMENT", "poll_interval_sec must be > 0")
        if max_wait_sec <= 0:
            raise AppError("INVALID_ARGUMENT", "max_wait_sec must be > 0")
        recent_steps_limit = int(arguments.get("recent_steps_limit", 3))
        stream_limit = int(arguments.get("stream_limit", 60))
        if stream_limit <= 0:
            raise AppError("INVALID_ARGUMENT", "stream_limit must be > 0")
        start_payload = self.start_game_flow_live(arguments)
        run_id = str(start_payload.get("run_id", "")).strip()
        if not run_id:
            raise AppError("INVALID_STATE", "start_game_flow_live returned empty run_id")
        poll_args = dict(arguments)
        poll_args["run_id"] = run_id
        poll_args["view"] = "chat"
        poll_args["recent_steps_limit"] = recent_steps_limit
        poll_args["event_limit"] = max(1, int(arguments.get("event_limit", 1)))
        snapshots: list[dict[str, Any]] = []
        poll_count = 0
        started_monotonic = time.monotonic()
        final_snapshot: dict[str, Any] = {}
        timed_out = False
        event_cursor = -1
        while True:
            poll_args["event_since"] = event_cursor
            snapshot = self.get_live_flow_progress(poll_args)
            poll_count += 1
            final_snapshot = snapshot if isinstance(snapshot, dict) else {}
            step_events = final_snapshot.get("step_events", {}) if isinstance(final_snapshot, dict) else {}
            if isinstance(step_events, dict):
                try:
                    event_cursor = int(step_events.get("cursor", event_cursor))
                except (TypeError, ValueError):
                    pass
            snapshots.append(build_stream_entry(final_snapshot))
            if len(snapshots) > stream_limit:
                snapshots = snapshots[-stream_limit:]
            state = str(final_snapshot.get("state", "")).strip().lower()
            if state == "finished":
                break
            if (time.monotonic() - started_monotonic) >= float(max_wait_sec):
                timed_out = True
                break
            time.sleep(poll_interval_sec)
        return {
            "run_id": run_id,
            "status": "timeout" if timed_out else "finished",
            "poll_count": poll_count,
            "poll_interval_sec": poll_interval_sec,
            "max_wait_sec": max_wait_sec,
            "stream_limit": stream_limit,
            "stream": snapshots,
            "started": start_payload,
            "final": final_snapshot,
        }
