from __future__ import annotations

import json
from pathlib import Path


def default_executable_config_path(project_root: Path) -> Path:
    return project_root / "tools" / "game-test-runner" / "config" / "godot_executable.json"


def load_godot_executable(project_root: Path) -> str:
    config_path = default_executable_config_path(project_root)
    if not config_path.is_file():
        raise FileNotFoundError(f"godot executable config not found: {config_path}")
    data = json.loads(config_path.read_text(encoding="utf-8"))
    value = str(data.get("godot_executable", "")).strip()
    if not value:
        raise ValueError(f"godot_executable missing in {config_path}")
    return value


def configure_godot_executable(project_root: Path, executable: str) -> Path:
    target = default_executable_config_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"godot_executable": executable}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target

