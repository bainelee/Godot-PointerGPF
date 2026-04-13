from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any


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
    observed_behavior = _clean_text(getattr(args, "bug_report", None))
    expected_behavior = _clean_text(getattr(args, "expected_behavior", None))
    summary = _clean_text(getattr(args, "bug_summary", None)) or _first_sentence(observed_behavior)
    steps_raw = _clean_text(getattr(args, "steps_to_trigger", None))
    location_scene = _clean_text(getattr(args, "location_scene", None))
    location_node = _clean_text(getattr(args, "location_node", None))
    location_script = _clean_text(getattr(args, "location_script", None))

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
        "frequency_hint": _clean_text(getattr(args, "frequency_hint", None)),
        "severity_hint": _clean_text(getattr(args, "severity_hint", None)),
        "extra_context": {
            "user_words": observed_behavior,
        },
    }
