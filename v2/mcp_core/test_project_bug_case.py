from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .test_project_bug_round import round_dir


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _timestamp(*, now_fn: Callable[[], datetime] = datetime.now) -> str:
    return now_fn().isoformat(timespec="seconds")


def bug_case_path(project_root: Path, round_id: str, bug_id: str) -> Path:
    return (round_dir(project_root, round_id) / "bug_cases" / f"{bug_id}.json").resolve()


def load_bug_case(path: str | Path) -> dict[str, Any]:
    return _load_json(Path(path).resolve())


def load_bug_case_from_args(args: Any) -> dict[str, Any]:
    bug_case_file = str(getattr(args, "bug_case_file", "") or "").strip()
    if not bug_case_file:
        return {}
    return load_bug_case(bug_case_file)


def _normalize_steps(raw_steps: Any) -> list[str]:
    if isinstance(raw_steps, list):
        return [str(item).strip() for item in raw_steps if str(item).strip()]
    text = str(raw_steps or "").strip()
    return [part.strip() for part in text.split("|") if part.strip()]


def create_bug_case(
    project_root: Path,
    round_id: str,
    bug_id: str,
    *,
    injected_bug_kind: str,
    affected_files: list[dict[str, Any]],
    bug_report_payload: dict[str, Any],
    expected_verification_target: dict[str, Any],
    now_fn: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    cleaned_round_id = str(round_id or "").strip()
    cleaned_bug_id = str(bug_id or "").strip()
    if not cleaned_round_id or not cleaned_bug_id:
        raise ValueError("round_id and bug_id are required for bug-case creation")
    payload = {
        "schema": "pointer_gpf.v2.test_project_bug_case.v1",
        "project_root": str(project_root.resolve()),
        "round_id": cleaned_round_id,
        "bug_id": cleaned_bug_id,
        "bug_source": "injected",
        "injected_bug_kind": str(injected_bug_kind or "").strip(),
        "affected_files": affected_files,
        "bug_report_payload": {
            "bug_report": str(bug_report_payload.get("bug_report", "")).strip(),
            "bug_summary": str(bug_report_payload.get("bug_summary", "")).strip(),
            "expected_behavior": str(bug_report_payload.get("expected_behavior", "")).strip(),
            "steps_to_trigger": _normalize_steps(bug_report_payload.get("steps_to_trigger", [])),
            "location_scene": str(bug_report_payload.get("location_scene", "")).strip(),
            "location_node": str(bug_report_payload.get("location_node", "")).strip(),
            "location_script": str(bug_report_payload.get("location_script", "")).strip(),
            "frequency_hint": str(bug_report_payload.get("frequency_hint", "")).strip(),
            "severity_hint": str(bug_report_payload.get("severity_hint", "")).strip(),
        },
        "expected_verification_target": expected_verification_target,
        "created_at": _timestamp(now_fn=now_fn),
    }
    target_path = bug_case_path(project_root, cleaned_round_id, cleaned_bug_id)
    payload["bug_case_file"] = str(_write_json(target_path, payload))
    return payload


def merged_bug_report_payload(args: Any) -> dict[str, str]:
    bug_case = load_bug_case_from_args(args)
    from_case = bug_case.get("bug_report_payload", {}) if isinstance(bug_case, dict) else {}
    if not isinstance(from_case, dict):
        from_case = {}

    def pick(field_name: str) -> str:
        raw_arg = getattr(args, field_name, None)
        if raw_arg not in {None, ""}:
            return str(raw_arg).strip()
        value = from_case.get(field_name, "")
        if field_name == "steps_to_trigger" and isinstance(value, list):
            return "|".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "").strip()

    return {
        "bug_report": pick("bug_report"),
        "bug_summary": pick("bug_summary"),
        "expected_behavior": pick("expected_behavior"),
        "steps_to_trigger": pick("steps_to_trigger"),
        "location_scene": pick("location_scene"),
        "location_node": pick("location_node"),
        "location_script": pick("location_script"),
        "frequency_hint": pick("frequency_hint"),
        "severity_hint": pick("severity_hint"),
    }


def bug_case_request_metadata(args: Any) -> dict[str, str]:
    bug_case = load_bug_case_from_args(args)
    if not bug_case:
        return {
            "bug_case_file": str(getattr(args, "bug_case_file", "") or "").strip(),
            "round_id": str(getattr(args, "round_id", "") or "").strip(),
            "bug_id": str(getattr(args, "bug_id", "") or "").strip(),
            "bug_source": "pre_existing",
            "injected_bug_kind": str(getattr(args, "bug_kind", "") or "").strip(),
        }
    return {
        "bug_case_file": str(bug_case.get("bug_case_file", "")).strip() or str(getattr(args, "bug_case_file", "") or "").strip(),
        "round_id": str(bug_case.get("round_id", "")).strip(),
        "bug_id": str(bug_case.get("bug_id", "")).strip(),
        "bug_source": str(bug_case.get("bug_source", "injected")).strip() or "injected",
        "injected_bug_kind": str(bug_case.get("injected_bug_kind", "")).strip(),
    }
