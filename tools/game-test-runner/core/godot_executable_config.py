"""从项目内配置文件读取 Godot 可执行路径（供 GameplayFlow / MCP / 脚本共用）。"""

from __future__ import annotations

import json
from pathlib import Path


def config_path_for_project(project_root: Path) -> Path:
    return Path(project_root).resolve() / "tools" / "game-test-runner" / "config" / "godot_executable.json"


def load_godot_executable_from_project_config(project_root: Path | None) -> str:
    if project_root is None:
        return ""
    path = config_path_for_project(project_root)
    if not path.is_file():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(raw, dict):
        return ""
    for key in ("godot_executable", "godot_bin", "GODOT_BIN"):
        val = str(raw.get(key, "")).strip()
        if val:
            return val
    return ""
