"""Parse GDScript _ready() visibility assignments and main-scene PackedScene instance mapping."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _res_to_rel(res: str) -> str:
    return res.replace("res://", "").lstrip("/")


def _ext_id_map_tscn(tscn_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in tscn_text.splitlines():
        s = line.strip()
        if not s.startswith("[ext_resource"):
            continue
        id_m = re.search(r'(?<![a-zA-Z])id="([^"]+)"', s)
        path_m = re.search(r'path="(res://[^"]+)"', s)
        if id_m and path_m:
            out[id_m.group(1)] = _res_to_rel(path_m.group(1))
    return out


def collect_gd_script_paths_from_tscn(project_root: Path, tscn_text: str) -> list[str]:
    id_map = _ext_id_map_tscn(tscn_text)
    out: list[str] = []
    for line in tscn_text.splitlines():
        if "script = ExtResource" not in line:
            continue
        m = re.search(r'ExtResource\("([^"]+)"\)', line)
        if not m:
            continue
        rel = id_map.get(m.group(1), "")
        if rel.endswith(".gd"):
            out.append(rel)
    return list(dict.fromkeys(out))


def packed_instance_children(tscn_text: str) -> dict[str, str]:
    """instance node name -> packed scene path rel."""
    id_map = _ext_id_map_tscn(tscn_text)
    out: dict[str, str] = {}
    for line in tscn_text.splitlines():
        if "instance=ExtResource" not in line:
            continue
        nm = re.search(r'name="([^"]+)"', line)
        ext = re.search(r'instance=ExtResource\("([^"]+)"\)', line)
        if nm and ext:
            p = id_map.get(ext.group(1), "")
            if p.endswith(".tscn"):
                out[nm.group(1)] = p.replace("\\", "/")
    return out


_ONREADY_DOLLAR = re.compile(r"@onready\s+var\s+(\w+)\s*:\s*[^=\n]+=\s*\$(\w+)")
_VISIBLE_ASSIGN = re.compile(r"(\$?)(\w+)\.visible\s*=\s*(true|false)")


def parse_onready_var_to_node(gd_text: str) -> dict[str, str]:
    """lower(var_name) -> Godot child node name from $Child."""
    return {m.group(1).lower(): m.group(2) for m in _ONREADY_DOLLAR.finditer(gd_text)}


def extract_ready_function_body(gd_text: str) -> str:
    m = re.search(r"^func\s+_ready\s*\([^)]*\)\s*(?:->\s*\w+\s*)?:", gd_text, flags=re.MULTILINE)
    if not m:
        return ""
    rest = gd_text[m.end() :]
    lines = rest.splitlines()
    body: list[str] = []
    base_indent: int | None = None
    for line in lines:
        if not line.strip():
            body.append(line)
            continue
        indent = len(line) - len(line.lstrip("\t"))
        if base_indent is None:
            base_indent = indent
            body.append(line)
            continue
        stripped = line.lstrip("\t")
        if stripped.startswith("func ") and indent <= base_indent:
            break
        body.append(line)
    return "\n".join(body)


def visibility_assignments_from_ready_bodies(gd_texts: list[str]) -> list[tuple[str, str, bool]]:
    """(kind, ident, visible) where kind is 'node' (literal node name) or 'var'."""
    out: list[tuple[str, str, bool]] = []
    for gd in gd_texts:
        body = extract_ready_function_body(gd)
        if not body:
            continue
        for m in _VISIBLE_ASSIGN.finditer(body):
            dollar, ident, val = m.group(1), m.group(2), m.group(3) == "true"
            if dollar:
                out.append(("node", ident, val))
            else:
                out.append(("var", ident, val))
    return out


def main_scene_packed_hidden_by_scripts(project_root: Path, main_scene_rel: str) -> dict[str, bool]:
    """
    For each PackedScene path used under main scene, True if a menu script's _ready sets
    the corresponding instance node to visible=false.
    """
    path = project_root / main_scene_rel
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    inst = packed_instance_children(text)
    if not inst:
        return {}
    gd_rels = collect_gd_script_paths_from_tscn(project_root, text)
    gd_texts = []
    for rel in gd_rels:
        gp = project_root / rel
        if gp.is_file():
            gd_texts.append(gp.read_text(encoding="utf-8", errors="replace"))

    hidden_scenes: dict[str, bool] = {}
    var_maps = [parse_onready_var_to_node(g) for g in gd_texts]
    assigns = visibility_assignments_from_ready_bodies(gd_texts)
    for kind, ident, vis in assigns:
        node_name: str | None = None
        if kind == "node":
            node_name = ident
        else:
            for vm in var_maps:
                node_name = vm.get(ident.lower())
                if node_name:
                    break
        if not node_name or vis:
            continue
        packed = inst.get(node_name)
        if packed:
            hidden_scenes[packed] = True
    return hidden_scenes


def apply_script_visibility_overrides(
    nodes: list[Any],
    gd_texts: list[str],
    *,
    parse_visible_fn: Any,
) -> dict[str, bool]:
    """Effective visible per node name after applying .tscn default then _ready assignments."""
    by_name = {n.name: n for n in nodes}
    state: dict[str, bool] = {n.name: parse_visible_fn(n) for n in nodes}
    var_maps = [parse_onready_var_to_node(g) for g in gd_texts]
    assigns = visibility_assignments_from_ready_bodies(gd_texts)
    for kind, ident, vis in assigns:
        if kind == "node":
            if ident in state:
                state[ident] = vis
        else:
            for vm in var_maps:
                nn = vm.get(ident.lower())
                if nn and nn in state:
                    state[nn] = vis
                    break
    return state
