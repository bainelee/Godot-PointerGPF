from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from flow_timeline_chat_map import human_step_and_goal
from flow_timeline_events import build_step_events


def read_flow_timeline_payload(
    run_id: str,
    run_root: Path,
    report: dict[str, Any],
    flow_report: dict[str, Any],
    to_posix: Callable[[str | Path], str],
    view: str = "full",
    recent_steps_limit: int = 3,
    chat_mode: str = "normal",
    event_since: int = -1,
    event_limit: int = 20,
) -> dict[str, Any]:
    report_status = str(report.get("status", "unknown")) if isinstance(report, dict) else "unknown"
    report_result_status = str(report.get("result_status", "")) if isinstance(report, dict) else ""
    timeline_path = run_root / "step_timeline.json"
    timeline_steps: list[dict[str, Any]] = []
    if timeline_path.exists():
        timeline_steps = _read_step_timeline(timeline_path)
    if not timeline_steps:
        timeline_steps = _read_driver_flow_fallback(run_root)
    timeline_steps = sorted(timeline_steps, key=lambda s: int(s.get("index", 0)))
    planned_total = 0
    planned_steps_raw = flow_report.get("driver_steps", []) if isinstance(flow_report, dict) else []
    if isinstance(planned_steps_raw, list):
        planned_total = len(planned_steps_raw)
    failed_step = next((s for s in timeline_steps if str(s.get("status", "")) == "failed"), None)
    last_step = timeline_steps[-1] if timeline_steps else None
    current_step = failed_step or last_step or {}
    passed_count = len([s for s in timeline_steps if str(s.get("status", "")) == "passed"])
    failed_count = len([s for s in timeline_steps if str(s.get("status", "")) == "failed"])
    skipped_count = len([s for s in timeline_steps if str(s.get("status", "")) == "skipped"])
    total_steps = max(len(timeline_steps), planned_total)
    full_payload = {
        "run_id": run_id,
        "artifact_root": to_posix(run_root),
        "flow_id": str(flow_report.get("flow_id", flow_report.get("flowId", ""))),
        "flow_status": str(flow_report.get("status", "")),
        "report_status": report_status,
        "report_result_status": report_result_status,
        "summary": {
            "total_steps": total_steps,
            "passed": passed_count,
            "failed": failed_count,
            "skipped": skipped_count,
        },
        "current_step": {
            "step_id": str(current_step.get("step_id", "")),
            "status": str(current_step.get("status", "")),
            "action": str(current_step.get("action", "")),
            "actual": str(current_step.get("actual", "")),
        },
        "steps": timeline_steps,
    }
    predicted_step = _predict_next_step(flow_report, full_payload["summary"] if isinstance(full_payload.get("summary"), dict) else {})
    if view != "chat":
        return full_payload
    limit = max(1, int(recent_steps_limit))
    recent_steps = timeline_steps[-limit:] if timeline_steps else []
    last_evidence = current_step.get("evidence_files", []) if isinstance(current_step, dict) else []
    if not isinstance(last_evidence, list):
        last_evidence = []
    failed_steps = [s for s in timeline_steps if str(s.get("status", "")) == "failed"]
    key_screenshot_cards = _collect_key_screenshot_cards(run_root, recent_steps, current_step)
    key_screenshots = [str(c.get("path", "")) for c in key_screenshot_cards if str(c.get("path", "")).strip()]
    normalized_chat_mode = str(chat_mode or "normal").strip().lower()
    if normalized_chat_mode not in {"normal", "short"}:
        normalized_chat_mode = "normal"
    chat_progress = _build_chat_progress(
        flow_id=str(full_payload["flow_id"]),
        flow_status=str(full_payload["flow_status"]),
        summary=full_payload["summary"] if isinstance(full_payload.get("summary"), dict) else {},
        current_step=full_payload["current_step"] if isinstance(full_payload.get("current_step"), dict) else {},
        key_screenshot_cards=key_screenshot_cards,
        predicted_step=predicted_step,
    )
    chat_progress_short = _build_chat_progress_short(
        flow_id=str(full_payload["flow_id"]),
        flow_status=str(full_payload["flow_status"]),
        summary=full_payload["summary"] if isinstance(full_payload.get("summary"), dict) else {},
        current_step=full_payload["current_step"] if isinstance(full_payload.get("current_step"), dict) else {},
        key_screenshot_cards=key_screenshot_cards,
        predicted_step=predicted_step,
    )
    selected_chat_progress = chat_progress_short if normalized_chat_mode == "short" else chat_progress
    step_events = build_step_events(
        run_root=run_root,
        flow_report=flow_report,
        summary=full_payload["summary"] if isinstance(full_payload.get("summary"), dict) else {},
        human_step_goal_fn=human_step_and_goal,
        event_since=event_since,
        event_limit=event_limit,
    )
    return {
        "run_id": full_payload["run_id"],
        "flow_id": full_payload["flow_id"],
        "flow_status": full_payload["flow_status"],
        "artifact_root": full_payload["artifact_root"],
        "summary": full_payload["summary"],
        "current_step": full_payload["current_step"],
        "recent_steps": [
            {
                "step_id": str(s.get("step_id", "")),
                "status": str(s.get("status", "")),
                "description": str(s.get("description", "")),
                "actual": str(s.get("actual", "")),
                "evidence_files": s.get("evidence_files", []) if isinstance(s.get("evidence_files", []), list) else [],
            }
            for s in recent_steps
        ],
        "chat_mode": normalized_chat_mode,
        "chat_progress": selected_chat_progress,
        "chat_progress_short": chat_progress_short,
        "predicted_next_step": predicted_step,
        "step_events": step_events,
        "key_screenshot_cards": key_screenshot_cards,
        "key_screenshots": key_screenshots,
        "chat_card": {
            "headline": "flow failed at current step" if failed_steps else "flow progressing/finished",
            "current_step_id": str(full_payload["current_step"].get("step_id", "")),
            "current_step_status": str(full_payload["current_step"].get("status", "")),
            "current_step_actual": str(full_payload["current_step"].get("actual", "")),
            "evidence_hint": last_evidence[0] if last_evidence else "",
            "screenshot_hint": key_screenshots[0] if key_screenshots else "",
            "next_action_hint": (
                "open evidence and inspect failure_summary.json/report.json"
                if failed_steps
                else "continue flow or validate expected checkpoints"
            ),
        },
    }


def _read_step_timeline(path: Path) -> list[dict[str, Any]]:
    try:
        timeline_payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    raw_steps = timeline_payload.get("steps", []) if isinstance(timeline_payload, dict) else []
    if not isinstance(raw_steps, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            continue
        out.append(
            {
                "index": int(raw.get("index", idx)),
                "step_id": str(raw.get("step_id", "")),
                "action": str(raw.get("action", "")),
                "status": str(raw.get("status", "unknown")),
                "description": str(raw.get("description", "")),
                "expected": str(raw.get("expected", "")),
                "actual": str(raw.get("actual", "")),
                "evidence_files": raw.get("evidence_files", []) if isinstance(raw.get("evidence_files", []), list) else [],
            }
        )
    return out


def _read_driver_flow_fallback(run_root: Path) -> list[dict[str, Any]]:
    driver_path = run_root / "logs" / "driver_flow.json"
    if not driver_path.exists():
        return []
    try:
        driver_payload = json.loads(driver_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    raw_steps = driver_payload.get("steps", []) if isinstance(driver_payload, dict) else []
    if not isinstance(raw_steps, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            continue
        response = raw.get("response", {})
        if not isinstance(response, dict):
            response = {}
        evidence_files: list[str] = ["logs/driver_flow.json"]
        screenshot = str(response.get("screenshot", "")).strip()
        if screenshot:
            evidence_files.append(screenshot)
        out.append(
            {
                "index": idx,
                "step_id": str(raw.get("step_id", f"step_{idx + 1:02d}")),
                "action": str(raw.get("action", "")),
                "status": str(raw.get("status", "unknown")),
                "description": "driver step",
                "expected": "driver response status == ok",
                "actual": str(raw.get("error", "")).strip() or "ok",
                "evidence_files": evidence_files,
            }
        )
    return out


def _collect_key_screenshot_cards(
    run_root: Path,
    recent_steps: list[dict[str, Any]],
    current_step: dict[str, Any],
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []

    def _push(paths: list[Any], step: dict[str, Any]) -> None:
        step_id = str(step.get("step_id", "")).strip()
        step_desc = str(step.get("description", "")).strip()
        for p in paths:
            raw = str(p or "").strip()
            if not raw:
                continue
            if raw.startswith("user://"):
                raw = raw.replace("user://", "screenshots/")
            if not raw.lower().endswith(".png"):
                continue
            abs_path = str((run_root / raw).as_posix()) if raw.startswith("screenshots/") else raw
            label = _infer_screenshot_label(raw, step_id, step_desc)
            candidates.append(
                {
                    "path": abs_path,
                    "label": label,
                    "source_step_id": step_id,
                }
            )

    if isinstance(current_step, dict):
        evidence = current_step.get("evidence_files", [])
        if isinstance(evidence, list):
            _push(evidence, current_step)
    for step in reversed(recent_steps):
        evidence = step.get("evidence_files", []) if isinstance(step, dict) else []
        if isinstance(evidence, list):
            _push(evidence, step if isinstance(step, dict) else {})

    dedup: list[dict[str, str]] = []
    seen: set[str] = set()
    for card in candidates:
        path = str(card.get("path", "")).strip()
        if not path or path in seen:
            continue
        seen.add(path)
        dedup.append(card)
        if len(dedup) >= 3:
            break
    return dedup


def _infer_screenshot_label(raw_path: str, step_id: str, step_desc: str) -> str:
    name = Path(raw_path).name.lower()
    if "room_detail" in name:
        return "房间详情节点已打开"
    if "build_t0" in name:
        return "建造阶段起始截图"
    if "build_tmid" in name:
        return "建造阶段中间截图"
    if "build_tdone" in name:
        return "建造阶段完成截图"
    if "clean_t0" in name:
        return "清理阶段起始截图"
    if "clean_tmid" in name:
        return "清理阶段中间截图"
    if "clean_tdone" in name:
        return "清理阶段完成截图"
    if "flow_exploration_step_01" in name:
        return "探索流程步骤1截图"
    if "flow_exploration_step_02" in name:
        return "探索流程步骤2截图"
    if "flow_exploration_step_03" in name:
        return "探索流程步骤3截图"
    if step_desc:
        return f"关键节点截图（{step_desc}）"
    if step_id:
        return f"关键节点截图（{step_id}）"
    return "关键节点截图"


def _build_chat_progress(
    flow_id: str,
    flow_status: str,
    summary: dict[str, Any],
    current_step: dict[str, Any],
    key_screenshot_cards: list[dict[str, str]],
    predicted_step: dict[str, str] | None = None,
) -> dict[str, Any]:
    total = int(summary.get("total_steps", 0))
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    step_id = str(current_step.get("step_id", "")).strip() or "unknown_step"
    step_status = str(current_step.get("status", "")).strip() or "unknown"
    step_actual = str(current_step.get("actual", "")).strip() or "n/a"
    step_action = str(current_step.get("action", "")).strip()
    display_step_id = step_id
    display_step_status = step_status
    display_step_action = step_action
    if (
        flow_status != "passed"
        and failed == 0
        and isinstance(predicted_step, dict)
        and str(predicted_step.get("step_id", "")).strip()
    ):
        display_step_id = str(predicted_step.get("step_id", "")).strip()
        display_step_action = str(predicted_step.get("action", "")).strip()
        display_step_status = "running"
    doing_text, goal_text = human_step_and_goal(display_step_id, display_step_action)
    flow_name = flow_id or "flow"
    purpose = goal_text
    if flow_status == "passed":
        result = f"{flow_name} 已完成，{passed}/{total} 步通过。"
        next_action = "可打开 report.json / flow_report.json 复盘，或继续下一条 flow。"
    elif failed > 0 or step_status == "failed":
        result = f"{flow_name} 在当前步骤失败，实际结果：{step_actual}。"
        next_action = "优先打开 failure_summary.json 与关键截图定位问题。"
    else:
        result = f"{flow_name} 运行中，已通过 {passed}/{total}。"
        next_action = "继续轮询 get_live_flow_progress，直到 state=finished。"
    screenshot_lines: list[str] = []
    for idx, card in enumerate(key_screenshot_cards, start=1):
        label = str(card.get("label", "")).strip() or "关键节点截图"
        path = str(card.get("path", "")).strip()
        if not path:
            continue
        screenshot_lines.append(f"关键节点截图（{idx}/{len(key_screenshot_cards)}）：{label} -> {path}")
    done_for_display = passed
    if display_step_status == "running" and total > 0:
        done_for_display = min(total, passed + 1)
    return {
        "当前步骤": f"{doing_text}（{display_step_status}）",
        "目的": purpose,
        "结果": result,
        "下一步": next_action,
        "进度": f"{done_for_display}/{total}",
        "截图简报": screenshot_lines,
    }


def _build_chat_progress_short(
    flow_id: str,
    flow_status: str,
    summary: dict[str, Any],
    current_step: dict[str, Any],
    key_screenshot_cards: list[dict[str, str]],
    predicted_step: dict[str, str] | None = None,
) -> dict[str, Any]:
    total = int(summary.get("total_steps", 0))
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    step_id = str(current_step.get("step_id", "")).strip() or "unknown_step"
    step_status = str(current_step.get("status", "")).strip() or "unknown"
    step_action = str(current_step.get("action", "")).strip()
    display_step_id = step_id
    display_step_status = step_status
    display_step_action = step_action
    if (
        flow_status != "passed"
        and failed == 0
        and isinstance(predicted_step, dict)
        and str(predicted_step.get("step_id", "")).strip()
    ):
        display_step_id = str(predicted_step.get("step_id", "")).strip()
        display_step_action = str(predicted_step.get("action", "")).strip()
        display_step_status = "running"
    doing_text, goal_text = human_step_and_goal(display_step_id, display_step_action)
    done_for_display = passed
    if display_step_status == "running" and total > 0:
        done_for_display = min(total, passed + 1)
    current_line = f"{doing_text}（{display_step_status}），进度 {done_for_display}/{total}。"
    if flow_status == "passed":
        result_line = f"已完成，失败 {failed}。"
        next_line = "进入复盘或执行下一条 flow。"
    elif failed > 0 or step_status == "failed":
        result_line = "当前步骤失败。"
        next_line = "打开 failure_summary.json 与证据定位原因。"
    else:
        result_line = "仍在执行中。"
        next_line = "继续轮询直到 state=finished。"
    screenshot_lines: list[str] = []
    if key_screenshot_cards:
        first = key_screenshot_cards[0]
        label = str(first.get("label", "")).strip() or "关键节点截图"
        path = str(first.get("path", "")).strip()
        if path:
            screenshot_lines.append(f"{label} -> {path}")
    return {
        "当前步骤": current_line,
        "目的": goal_text,
        "结果": result_line,
        "下一步": next_line,
        "截图简报": screenshot_lines,
    }


def _predict_next_step(flow_report: dict[str, Any], summary: dict[str, Any]) -> dict[str, str]:
    if not isinstance(flow_report, dict) or not isinstance(summary, dict):
        return {}
    raw_steps = flow_report.get("driver_steps", [])
    if not isinstance(raw_steps, list) or not raw_steps:
        return {}
    try:
        passed = int(summary.get("passed", 0))
    except (TypeError, ValueError):
        passed = 0
    if passed < 0 or passed >= len(raw_steps):
        return {}
    next_raw = raw_steps[passed]
    if not isinstance(next_raw, dict):
        return {}
    return {
        "step_id": str(next_raw.get("id", "")),
        "action": str(next_raw.get("action", "")),
    }
