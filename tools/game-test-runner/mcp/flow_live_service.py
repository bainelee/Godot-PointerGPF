from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_live_start_payload(
    run_id: str,
    flow_file: Path,
    run_root: Path,
    stdout_path: Path,
    stderr_path: Path,
    requested_godot_bin: str,
    resolved_godot_bin: str,
    godot_bin_resolution: dict[str, Any],
    pid: int,
    to_posix,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "started",
        "pid": int(pid),
        "flow_file": to_posix(flow_file),
        "artifact_root": to_posix(run_root),
        "stdout_log": to_posix(stdout_path),
        "stderr_log": to_posix(stderr_path),
        "godot_bin_requested": requested_godot_bin,
        "godot_bin_resolved": resolved_godot_bin,
        "godot_bin_resolution": godot_bin_resolution,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def resolve_live_state(run_root: Path) -> str:
    if (run_root / "report.json").exists():
        return "finished"
    if not (run_root / "run_meta.json").exists():
        return "pending"
    return "running"


def build_stream_entry(final_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "polled_at": datetime.now(timezone.utc).isoformat(),
        "state": str(final_snapshot.get("state", "unknown")),
        "summary": final_snapshot.get("summary", {}),
        "current_step": final_snapshot.get("current_step", {}),
        "chat_progress": final_snapshot.get("chat_progress", {}),
        "chat_progress_short": final_snapshot.get("chat_progress_short", {}),
        "key_screenshot_cards": final_snapshot.get("key_screenshot_cards", []),
    }

