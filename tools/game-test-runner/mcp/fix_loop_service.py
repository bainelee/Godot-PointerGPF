from __future__ import annotations

from typing import Any


def normalize_bounded_auto_fix(raw_value: Any) -> int:
    try:
        bounded_auto_fix = int(raw_value)
    except (TypeError, ValueError):
        bounded_auto_fix = 0
    if bounded_auto_fix <= 0:
        return 0
    return min(3, bounded_auto_fix)


def default_fix_loop_payload() -> dict[str, Any]:
    return {
        "enabled": False,
        "max_rounds": 0,
        "rounds_executed": 0,
        "approval_required": False,
        "status": "not_enabled",
        "rounds": [],
    }

