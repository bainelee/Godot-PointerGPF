from __future__ import annotations

import shutil
import re
from pathlib import Path


_MAIN_SCENE_UID_RE = re.compile(r'^run/main_scene="(uid://[^"]+)"\s*$', re.MULTILINE)


def _resolve_uid_scene_path(project_root: Path, uid: str) -> str | None:
    for path in sorted(project_root.rglob("*.tscn")):
        try:
            head = path.read_text(encoding="utf-8")[:400]
        except OSError:
            continue
        if f'uid="{uid}"' in head:
            rel = str(path.relative_to(project_root)).replace("\\", "/")
            return f"res://{rel}"
    return None


def _ensure_plugin_enabled(project_root: Path) -> None:
    project_file = project_root / "project.godot"
    if not project_file.is_file():
        raise FileNotFoundError(f"project.godot not found: {project_file}")
    text = project_file.read_text(encoding="utf-8")
    uid_match = _MAIN_SCENE_UID_RE.search(text)
    if uid_match:
        resolved = _resolve_uid_scene_path(project_root, uid_match.group(1))
        if resolved:
            text = text.replace(uid_match.group(0), f'run/main_scene="{resolved}"')
    text = re.sub(r'^\s*PointerGPFRuntimeBridge="[^"]*"\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*PointerGPFV2RuntimeBridge="[^"]*"\s*$', '', text, flags=re.MULTILINE)
    autoload_entry = 'PointerGPFV2RuntimeBridge="*res://addons/pointer_gpf/runtime_bridge.gd"'
    plugin_entry = 'enabled=PackedStringArray("res://addons/pointer_gpf/plugin.cfg")'
    if "[autoload]" in text:
        lines = text.splitlines()
        out: list[str] = []
        in_autoload = False
        inserted = False
        for line in lines:
            stripped = line.strip()
            if stripped == "[autoload]":
                in_autoload = True
                out.append(line)
                continue
            if in_autoload and stripped.startswith("[") and stripped.endswith("]"):
                if not inserted:
                    out.append(autoload_entry)
                    inserted = True
                in_autoload = False
            out.append(line)
        if in_autoload and not inserted:
            out.append(autoload_entry)
        text = "\n".join(out) + ("\n" if not text.endswith("\n") else "")
    else:
        suffix = "" if text.endswith("\n") or text == "" else "\n"
        text = text + suffix + "\n[autoload]\n" + autoload_entry + "\n"
    if "[editor_plugins]" in text:
        lines = text.splitlines()
        out: list[str] = []
        in_editor_plugins = False
        replaced = False
        for line in lines:
            stripped = line.strip()
            if stripped == "[editor_plugins]":
                in_editor_plugins = True
                out.append(line)
                continue
            if in_editor_plugins and stripped.startswith("[") and stripped.endswith("]"):
                if not replaced:
                    out.append(plugin_entry)
                    replaced = True
                in_editor_plugins = False
            if in_editor_plugins and stripped.startswith("enabled="):
                out.append(plugin_entry)
                replaced = True
                continue
            out.append(line)
        if in_editor_plugins and not replaced:
            out.append(plugin_entry)
        text = "\n".join(out) + ("\n" if not text.endswith("\n") else "")
    else:
        suffix = "" if text.endswith("\n") or text == "" else "\n"
        text = text + suffix + "\n[editor_plugins]\n" + plugin_entry + "\n"
    project_file.write_text(text, encoding="utf-8")


def sync_plugin(plugin_source_root: Path, project_root: Path) -> Path:
    src = plugin_source_root.resolve()
    dst = (project_root / "addons" / "pointer_gpf").resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"plugin source not found: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)
    _ensure_plugin_enabled(project_root.resolve())
    return dst
