from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from .test_project_bug_case import bug_case_request_metadata, merged_bug_report_payload


def _clean_text(raw: Any) -> str:
    return str(raw or "").strip()


def _first_sentence(text: str) -> str:
    normalized = text.replace("\r", " ").replace("\n", " ").strip()
    for separator in ("。", ".", "！", "!", "？", "?"):
        if separator in normalized:
            head = normalized.split(separator, 1)[0].strip()
            if head:
                return head
    return normalized


def collect_bug_report(project_root: Path, args: Namespace) -> dict[str, Any]:
    merged = merged_bug_report_payload(args)
    observed_behavior = _clean_text(merged.get("bug_report", ""))
    expected_behavior = _clean_text(merged.get("expected_behavior", ""))
    summary = _clean_text(getattr(args, "bug_summary", None)) or _clean_text(merged.get("bug_summary", "")) or _first_sentence(observed_behavior)
    steps_raw = _clean_text(merged.get("steps_to_trigger", ""))
    location_scene = _clean_text(merged.get("location_scene", ""))
    location_node = _clean_text(merged.get("location_node", ""))
    location_script = _clean_text(merged.get("location_script", ""))
    bug_case_metadata = bug_case_request_metadata(args)

    missing_fields: list[str] = []
    if not observed_behavior:
        missing_fields.append("bug_report")
    if not expected_behavior:
        missing_fields.append("expected_behavior")
    if not (summary or steps_raw or location_scene or location_node or location_script):
        missing_fields.append("summary_or_steps_or_location")
    if missing_fields:
        raise ValueError(
            "collect_bug_report requires bug_report and expected_behavior, plus at least one summary/steps/location hint"
        )

    steps_to_trigger = [part.strip() for part in steps_raw.split("|") if part.strip()]
    return {
        "schema": "pointer_gpf.v2.bug_intake.v1",
        "project_root": str(project_root.resolve()),
        "summary": summary,
        "steps_to_trigger": steps_to_trigger,
        "observed_behavior": observed_behavior,
        "expected_behavior": expected_behavior,
        "location_hint": {
            "scene": location_scene,
            "node": location_node,
            "script": location_script,
        },
        "frequency_hint": _clean_text(merged.get("frequency_hint", "")),
        "severity_hint": _clean_text(merged.get("severity_hint", "")),
        "extra_context": {
            "user_words": observed_behavior,
        },
        "bug_case_file": str(bug_case_metadata.get("bug_case_file", "")).strip(),
        "round_id": str(bug_case_metadata.get("round_id", "")).strip(),
        "bug_id": str(bug_case_metadata.get("bug_id", "")).strip(),
        "bug_source": str(bug_case_metadata.get("bug_source", "pre_existing")).strip() or "pre_existing",
        "injected_bug_kind": str(bug_case_metadata.get("injected_bug_kind", "")).strip(),
    }
