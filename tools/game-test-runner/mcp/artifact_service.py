from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_test_report_payload(
    run_id: str,
    run_root: Path,
    fmt: str,
) -> dict[str, Any]:
    if fmt == "json":
        report_path = run_root / "report.json"
        if not report_path.exists():
            return {}
        return {"run_id": run_id, "format": "json", "report": load_json_dict(report_path)}
    report_path = run_root / "report.md"
    if not report_path.exists():
        return {}
    return {"run_id": run_id, "format": "md", "report": report_path.read_text(encoding="utf-8")}


def load_flow_report(run_root: Path) -> dict[str, Any]:
    return load_json_dict(run_root / "flow_report.json")

