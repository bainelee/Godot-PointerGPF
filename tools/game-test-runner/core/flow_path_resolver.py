from __future__ import annotations

import json
from pathlib import Path


def _migration_map_path(project_root: Path) -> Path:
    return project_root / "flows" / "migration_map.json"


def _load_aliases(project_root: Path) -> dict[str, str]:
    path = _migration_map_path(project_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    aliases = payload.get("aliases", {}) if isinstance(payload, dict) else {}
    if not isinstance(aliases, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in aliases.items():
        key = str(k or "").replace("\\", "/").strip().lstrip("/")
        val = str(v or "").replace("\\", "/").strip().lstrip("/")
        if key and val:
            out[key] = val
    return out


def resolve_flow_path(project_root: Path, raw_flow_file: str) -> Path:
    raw = str(raw_flow_file or "").strip()
    if not raw:
        return Path("")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (project_root / raw).resolve()
    if candidate.exists():
        return candidate
    aliases = _load_aliases(project_root)
    rel = ""
    try:
        rel = candidate.resolve().relative_to(project_root.resolve()).as_posix()
    except Exception:
        pass
    rel_raw = str(raw).replace("\\", "/").strip().lstrip("/")
    mapped = aliases.get(rel) or aliases.get(rel_raw)
    if not mapped:
        return candidate
    mapped_path = (project_root / mapped).resolve()
    return mapped_path if mapped_path.exists() else candidate
