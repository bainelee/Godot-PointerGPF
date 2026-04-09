from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def read_driver_flow_events(run_root: Path, tail_lines: int = 400) -> tuple[list[dict[str, Any]], int]:
    path = run_root / "logs" / "driver_flow_events.jsonl"
    if not path.exists():
        return [], 0
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    total_lines = len(raw_lines)
    start_index = max(0, total_lines - max(1, int(tail_lines)))
    selected = raw_lines[start_index:]
    events: list[dict[str, Any]] = []
    for idx, line in enumerate(selected):
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payload["_global_index"] = start_index + idx
            events.append(payload)
    return events, total_lines


def build_step_events(
    run_root: Path,
    flow_report: dict[str, Any],
    summary: dict[str, Any],
    human_step_goal_fn: Callable[[str, str], tuple[str, str]],
    event_since: int = -1,
    event_limit: int = 20,
) -> dict[str, Any]:
    if not isinstance(flow_report, dict) or not isinstance(summary, dict):
        return {"started": {}, "completed": []}
    raw_steps = flow_report.get("driver_steps", [])
    if not isinstance(raw_steps, list) or not raw_steps:
        return {"started": {}, "completed": []}
    total = len(raw_steps)
    safe_since = max(-1, int(event_since))
    safe_limit = max(1, int(event_limit))
    tail_budget = max(200, safe_limit * 12)
    events, total_lines = read_driver_flow_events(run_root, tail_lines=tail_budget)
    if events:
        def _safe_int(val: Any, default: int = -1) -> int:
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        current_started: dict[str, Any] | None = None
        for event in events:
            event_type = str(event.get("type", "")).strip()
            if event_type == "step_started":
                current_started = event
                continue
            if event_type == "step_completed" and isinstance(current_started, dict):
                if _safe_int(current_started.get("index", -1)) == _safe_int(event.get("index", -2)):
                    current_started = None

        if safe_since < 0:
            candidate = events[-safe_limit:]
        else:
            candidate = [e for e in events if _safe_int(e.get("_global_index", -1)) > safe_since]
            candidate = candidate[:safe_limit]

        new_events: list[dict[str, Any]] = []
        completed_payload: list[dict[str, Any]] = []
        for event in candidate:
            idx = _safe_int(event.get("index", -1))
            step_id = str(event.get("step_id", ""))
            action = str(event.get("action", ""))
            if (not step_id or not action) and 0 <= idx < total:
                raw = raw_steps[idx]
                if isinstance(raw, dict):
                    step_id = step_id or str(raw.get("id", ""))
                    action = action or str(raw.get("action", ""))
            doing, goal = human_step_goal_fn(step_id, action)
            event_type = str(event.get("type", "")).strip()
            if event_type == "step_ready":
                event_kind = "ready"
            elif event_type == "step_started":
                event_kind = "started"
            else:
                event_kind = "completed"
            new_events.append(
                {
                    "kind": event_kind,
                    "step_id": step_id,
                    "action": action,
                    "text": doing,
                    "goal": goal,
                    "progress": f"{idx + 1}/{total}" if idx >= 0 else "",
                    "status": str(event.get("status", "running" if event_kind == "started" else "passed")),
                    "ts": str(event.get("ts", "")),
                }
            )
            if event_type == "step_completed":
                completed_payload.append(
                    {
                        "step_id": step_id,
                        "action": action,
                        "text": doing,
                        "goal": goal,
                        "progress": f"{idx + 1}/{total}" if idx >= 0 else "",
                        "status": str(event.get("status", "passed")) or "passed",
                        "ts": str(event.get("ts", "")),
                    }
                )

        started_payload: dict[str, Any] = {}
        if isinstance(current_started, dict) and safe_since < 0:
            idx = _safe_int(current_started.get("index", -1))
            step_id = str(current_started.get("step_id", ""))
            action = str(current_started.get("action", ""))
            if (not step_id or not action) and 0 <= idx < total:
                raw = raw_steps[idx]
                if isinstance(raw, dict):
                    step_id = step_id or str(raw.get("id", ""))
                    action = action or str(raw.get("action", ""))
            doing, goal = human_step_goal_fn(step_id, action)
            started_payload = {
                "step_id": step_id,
                "action": action,
                "text": doing,
                "goal": goal,
                "progress": f"{idx + 1}/{total}" if idx >= 0 else "",
                "status": "running",
                "ts": str(current_started.get("ts", "")),
            }

        returned_cursor = safe_since
        if candidate:
            returned_cursor = int(candidate[-1].get("_global_index", safe_since))
        elif safe_since < 0:
            returned_cursor = total_lines - 1
        return {
            "started": started_payload,
            "completed": completed_payload,
            "cursor": returned_cursor,
            "new_events": new_events,
        }

    try:
        passed = int(summary.get("passed", 0))
    except (TypeError, ValueError):
        passed = 0
    passed = max(0, min(total, passed))
    completed: list[dict[str, Any]] = []
    for idx in range(passed):
        raw = raw_steps[idx]
        if not isinstance(raw, dict):
            continue
        step_id = str(raw.get("id", ""))
        action = str(raw.get("action", ""))
        doing, goal = human_step_goal_fn(step_id, action)
        completed.append(
            {
                "step_id": step_id,
                "action": action,
                "text": doing,
                "goal": goal,
                "progress": f"{idx + 1}/{total}",
                "status": "passed",
            }
        )
    started: dict[str, Any] = {}
    if passed < total:
        raw = raw_steps[passed]
        if isinstance(raw, dict):
            step_id = str(raw.get("id", ""))
            action = str(raw.get("action", ""))
            doing, goal = human_step_goal_fn(step_id, action)
            started = {
                "step_id": step_id,
                "action": action,
                "text": doing,
                "goal": goal,
                "progress": f"{passed + 1}/{total}",
                "status": "running",
            }
    return {
        "started": started,
        "completed": completed[-3:] if completed else [],
        "cursor": -1,
        "new_events": [],
    }
