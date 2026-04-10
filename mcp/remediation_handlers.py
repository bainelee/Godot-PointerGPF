"""Registry of remediation handlers keyed by remediation_class (server registers implementations)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

HandlerFn = Callable[[Any, Path, dict[str, Any], dict[str, Any]], dict[str, Any]]

_REGISTRY: dict[str, HandlerFn] = {}


def register_handler(remediation_class: str, fn: HandlerFn) -> None:
    _REGISTRY[remediation_class] = fn


def clear_handlers() -> None:
    """Test-only: reset registry."""
    _REGISTRY.clear()


def run_handlers(
    remediation_class: str,
    ctx: Any,
    project_root: Path,
    tool_args: dict[str, Any],
    error_details: dict[str, Any],
) -> dict[str, Any]:
    fn = _REGISTRY.get(remediation_class)
    if fn is None:
        return {"handled": False, "actions": [], "notes": "no handler registered for class"}
    return fn(ctx, project_root, tool_args, error_details)
