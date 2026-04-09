#!/usr/bin/env python3
"""Parse gameplay flow files (JSON or YAML)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_flow_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        data = _parse_yaml(text)
    else:
        # Try JSON first, then YAML fallback.
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = _parse_yaml(text)
    if not isinstance(data, dict):
        raise ValueError("flow file must contain an object root")
    data.setdefault("steps", [])
    return data


def _parse_yaml(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pylint: disable=broad-except
        raise RuntimeError("YAML flow requires PyYAML installed") from exc
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("yaml flow root must be object")
    return data

