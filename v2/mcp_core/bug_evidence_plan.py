from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


ALLOWED_EVIDENCE_ACTIONS = {"wait", "click", "callmethod", "aimat", "shoot", "sample", "observe", "check"}
ALLOWED_EVIDENCE_PHASES = {"pre_trigger", "trigger_window", "post_trigger", "final_check"}
MAX_EVIDENCE_STEPS = 12
MAX_WINDOW_MS = 5000
MIN_INTERVAL_MS = 16


def _raw_plan_args(args: Any) -> tuple[str, str]:
    return (
        str(getattr(args, "evidence_plan_json", "") or "").strip(),
        str(getattr(args, "evidence_plan_file", "") or "").strip(),
    )


def _read_plan_file(project_root: Path, file_text: str) -> tuple[dict[str, Any] | None, str]:
    if not file_text:
        return None, ""
    path = Path(file_text)
    if not path.is_absolute():
        path = (project_root / path).resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return None, f"could not read evidence plan file: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"evidence plan file is not valid JSON: {exc}"
    return payload if isinstance(payload, dict) else None, "" if isinstance(payload, dict) else "evidence plan file root must be an object"


def _read_plan_json(raw_json: str) -> tuple[dict[str, Any] | None, str]:
    if not raw_json:
        return None, ""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return None, f"evidence plan JSON is not valid: {exc}"
    return payload if isinstance(payload, dict) else None, "" if isinstance(payload, dict) else "evidence plan JSON root must be an object"


def _contains_forbidden_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_forbidden_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_path(item) for item in value)
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    if text.startswith("file://"):
        return True
    if "..\\" in text or "../" in text:
        return True
    return bool(re.match(r"^[A-Za-z]:[\\/]", text))


def _normalize_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _evidence_key(step: dict[str, Any]) -> str:
    return str(step.get("evidenceKey", "") or step.get("evidence_key", "") or step.get("evidenceRef", "") or step.get("evidence_ref", "")).strip()


def _normalize_step(raw_step: dict[str, Any], index: int) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    step = deepcopy(raw_step)
    action = str(step.get("action", "")).strip()
    action_key = action.lower()
    if action_key not in ALLOWED_EVIDENCE_ACTIONS:
        reasons.append(f"step {index} uses unsupported action: {action}")

    phase = str(step.get("phase", "") or step.get("modelEvidencePhase", "") or "").strip()
    if not phase:
        phase = "final_check" if action_key == "check" else "post_trigger"
    if phase not in ALLOWED_EVIDENCE_PHASES:
        reasons.append(f"step {index} uses unsupported phase: {phase}")

    if _contains_forbidden_path(step):
        reasons.append(f"step {index} contains a filesystem-like path, which is not allowed in runtime evidence plans")

    step_id = str(step.get("id", "")).strip()
    if not step_id:
        step_id = f"model_evidence_step_{index}"
    if not re.match(r"^[A-Za-z0-9_\-]+$", step_id):
        reasons.append(f"step {index} id contains unsupported characters: {step_id}")

    if action_key == "sample":
        target = step.get("target", {})
        metric = step.get("metric", {})
        if not isinstance(target, dict):
            reasons.append(f"step {index} sample target must be an object")
        if not isinstance(metric, dict):
            reasons.append(f"step {index} sample metric must be an object")
        window_ms = _normalize_int(step.get("windowMs", step.get("window_ms", 0)), 0)
        interval_ms = _normalize_int(step.get("intervalMs", step.get("interval_ms", 0)), 0)
        if window_ms <= 0 or window_ms > MAX_WINDOW_MS:
            reasons.append(f"step {index} sample windowMs must be between 1 and {MAX_WINDOW_MS}")
        if interval_ms < MIN_INTERVAL_MS:
            reasons.append(f"step {index} sample intervalMs must be at least {MIN_INTERVAL_MS}")
        if not _evidence_key(step):
            reasons.append(f"step {index} sample requires evidenceKey")

    if action_key == "observe":
        event = step.get("event", {})
        if not isinstance(event, dict):
            reasons.append(f"step {index} observe event must be an object")
        window_ms = _normalize_int(step.get("windowMs", step.get("window_ms", 0)), 0)
        if window_ms <= 0 or window_ms > MAX_WINDOW_MS:
            reasons.append(f"step {index} observe windowMs must be between 1 and {MAX_WINDOW_MS}")
        if not _evidence_key(step):
            reasons.append(f"step {index} observe requires evidenceKey")

    if action_key == "check":
        if not _evidence_key(step) and not str(step.get("hint", "")).strip() and not str(step.get("checkType", "") or step.get("check_type", "")).strip():
            reasons.append(f"step {index} check requires evidenceRef, hint, or checkType")

    if action_key == "callmethod":
        target = step.get("target", {})
        method_name = str(step.get("method", "") or step.get("methodName", "") or step.get("method_name", "")).strip()
        if not isinstance(target, dict):
            reasons.append(f"step {index} callMethod target must be an object")
        if not method_name:
            reasons.append(f"step {index} callMethod requires method")
        args = step.get("args", [])
        if not isinstance(args, list):
            reasons.append(f"step {index} callMethod args must be a list when provided")

    if action_key == "aimat":
        target = step.get("target", {})
        player = step.get("player", {})
        if not isinstance(target, dict):
            reasons.append(f"step {index} aimAt target must be an object")
        if player not in ({}, None) and not isinstance(player, dict):
            reasons.append(f"step {index} aimAt player must be an object when provided")

    if action_key == "shoot":
        player = step.get("player", {})
        if player not in ({}, None) and not isinstance(player, dict):
            reasons.append(f"step {index} shoot player must be an object when provided")

    if reasons:
        return None, reasons

    step["id"] = step_id
    if action_key == "callmethod":
        step["action"] = "callMethod"
    elif action_key == "aimat":
        step["action"] = "aimAt"
    else:
        step["action"] = action_key if action_key != "closeproject" else "closeProject"
    step["phase"] = phase
    step["source"] = "model_evidence_plan"
    step["modelEvidencePhase"] = phase
    return step, []


def load_model_evidence_plan(project_root: Path, args: Any) -> dict[str, Any]:
    raw_json, raw_file = _raw_plan_args(args)
    if not raw_json and not raw_file:
        return {
            "status": "not_provided",
            "plan": {"steps": []},
            "rejected_reasons": [],
            "source": "",
        }

    payload: dict[str, Any] | None
    error = ""
    source = "json" if raw_json else "file"
    if raw_json:
        payload, error = _read_plan_json(raw_json)
    else:
        payload, error = _read_plan_file(project_root, raw_file)
    if payload is None:
        return {
            "status": "rejected",
            "plan": {"steps": []},
            "rejected_reasons": [error or "evidence plan could not be loaded"],
            "source": source,
        }

    raw_steps = payload.get("steps", [])
    if not isinstance(raw_steps, list):
        return {
            "status": "rejected",
            "plan": {"steps": []},
            "rejected_reasons": ["evidence plan steps must be a list"],
            "source": source,
        }
    if len(raw_steps) > MAX_EVIDENCE_STEPS:
        return {
            "status": "rejected",
            "plan": {"steps": []},
            "rejected_reasons": [f"evidence plan has too many steps: {len(raw_steps)} > {MAX_EVIDENCE_STEPS}"],
            "source": source,
        }

    steps: list[dict[str, Any]] = []
    rejected: list[str] = []
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            rejected.append(f"step {index} must be an object")
            continue
        normalized, reasons = _normalize_step(raw_step, index)
        if normalized is None:
            rejected.extend(reasons)
            continue
        steps.append(normalized)

    return {
        "status": "accepted" if not rejected else "rejected",
        "plan": {
            "schema": "pointer_gpf.v2.model_evidence_plan.v1",
            "steps": steps if not rejected else [],
        },
        "rejected_reasons": rejected,
        "source": source,
    }
