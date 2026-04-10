"""Parse Godot .tscn for static UI layout and click-likelihood heuristics (no runtime)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gdscript_ready_visibility import (
    apply_script_visibility_overrides,
    collect_gd_script_paths_from_tscn,
)

_NODE_HEADER = re.compile(
    r'^\[node\s+name="([^"]+)"\s+type="([^"]+)"(?:\s+parent="([^"]*)")?\]'
)


@dataclass
class ParsedNode:
    name: str
    type_name: str
    parent_path: str
    raw_attrs: dict[str, str] = field(default_factory=dict)


def parse_tscn_nodes(tscn_text: str) -> list[ParsedNode]:
    nodes: list[ParsedNode] = []
    current: ParsedNode | None = None
    for line in tscn_text.splitlines():
        m = _NODE_HEADER.match(line.strip())
        if m:
            name, typ, parent = m.group(1), m.group(2), m.group(3)
            parent_path = "." if parent is None else parent.strip()
            current = ParsedNode(name=name, type_name=typ, parent_path=parent_path, raw_attrs={})
            nodes.append(current)
            continue
        if current is None:
            continue
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith(";"):
            key, _, val = stripped.partition("=")
            current.raw_attrs[key.strip()] = val.strip()
    return nodes


def build_parent_map(nodes: list[ParsedNode]) -> tuple[str, dict[str, str | None]]:
    """First node is scene root. parent=\".\" means direct child of root."""
    if not nodes:
        return "", {}
    root = nodes[0].name
    parent_of: dict[str, str | None] = {root: None}
    for n in nodes:
        if n.name == root:
            continue
        pp = n.parent_path.strip()
        if pp in (".", "", "0"):
            parent_of[n.name] = root
        else:
            parent_of[n.name] = pp.split("/")[-1]
    return root, parent_of


def nodes_by_name(nodes: list[ParsedNode]) -> dict[str, ParsedNode]:
    return {n.name: n for n in nodes}


def ancestor_chain(nodes: list[ParsedNode], control_name: str) -> list[ParsedNode]:
    by = nodes_by_name(nodes)
    _, parent_of = build_parent_map(nodes)
    out: list[ParsedNode] = []
    cur = by.get(control_name)
    for _ in range(256):
        if cur is None:
            break
        out.append(cur)
        p = parent_of.get(cur.name)
        if p is None:
            break
        cur = by.get(p)
    return out


def read_viewport_size_from_project(project_godot: Path, default: tuple[int, int] = (1920, 1080)) -> tuple[int, int]:
    raw = project_godot.read_text(encoding="utf-8", errors="replace")
    mw = re.search(r"window/size/viewport_width\s*=\s*(\d+)", raw)
    mh = re.search(r"window/size/viewport_height\s*=\s*(\d+)", raw)
    if mw and mh:
        return int(mw.group(1)), int(mh.group(1))
    return default


def _float_attr(node: ParsedNode, key: str, default: float = 0.0) -> float:
    v = node.raw_attrs.get(key, "")
    if not v:
        return default
    token = v.split("(", 1)[-1].split(")", 1)[0].strip()
    try:
        return float(token)
    except ValueError:
        return default


def _is_interactive_control_type(type_name: str) -> bool:
    return "Button" in type_name or type_name in {"LineEdit", "TextEdit", "CheckBox", "Slider"}


def _control_like_rect(
    nodes: list[ParsedNode],
    node_name: str,
) -> tuple[float, float, float, float] | None:
    by = nodes_by_name(nodes)
    n = by.get(node_name)
    if not n:
        return None
    typ = n.type_name
    if typ not in {
        "Button",
        "TextureButton",
        "CheckBox",
        "ColorRect",
        "Panel",
        "Label",
        "MarginContainer",
        "VBoxContainer",
        "HBoxContainer",
        "Control",
    } and "Container" not in typ and "Button" not in typ:
        return None
    l = _float_attr(n, "offset_left")
    t = _float_attr(n, "offset_top")
    r = _float_attr(n, "offset_right")
    b = _float_attr(n, "offset_bottom")
    if r <= l or b <= t:
        return None
    return (l, t, r - l, b - t)


def _rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def control_screen_rect(
    nodes: list[ParsedNode],
    control_name: str,
    *,
    viewport: tuple[int, int],
) -> tuple[float, float, float, float] | None:
    by = nodes_by_name(nodes)
    n = by.get(control_name)
    if not n or not _is_interactive_control_type(n.type_name):
        return None
    l = _float_attr(n, "offset_left")
    t = _float_attr(n, "offset_top")
    r = _float_attr(n, "offset_right")
    b = _float_attr(n, "offset_bottom")
    if r <= l or b <= t:
        return None
    return (l, t, r - l, b - t)


def _parse_visible(node: ParsedNode) -> bool:
    v = node.raw_attrs.get("visible", "true").lower()
    return "false" not in v


def _parse_mouse_filter(node: ParsedNode) -> int:
    raw = node.raw_attrs.get("mouse_filter", "0")
    try:
        return int(raw.strip())
    except ValueError:
        return 0


def _modulate_alpha(mod: str) -> float | None:
    m = re.search(r"Color\s*\(([^)]+)\)", mod)
    if not m:
        return None
    parts = [p.strip() for p in m.group(1).split(",")]
    try:
        return float(parts[-1])
    except (IndexError, ValueError):
        return None


def _effective_visible(node: ParsedNode, visibility_override: dict[str, bool] | None) -> bool:
    if visibility_override is not None and node.name in visibility_override:
        return visibility_override[node.name]
    return _parse_visible(node)


def _later_sibling_occlusion_notes(
    nodes: list[ParsedNode],
    control_name: str,
    *,
    visibility_override: dict[str, bool] | None,
) -> list[str]:
    """Heuristic: later siblings under the same parent may draw on top (Godot tree order)."""
    by = nodes_by_name(nodes)
    target = by.get(control_name)
    if not target:
        return []
    pp = target.parent_path.strip()
    ordered = [n for n in nodes if n.parent_path.strip() == pp]
    try:
        idx = next(i for i, n in enumerate(ordered) if n.name == control_name)
    except StopIteration:
        return []
    trect = _control_like_rect(nodes, control_name)
    if not trect:
        return []
    notes: list[str] = []
    for later in ordered[idx + 1 :]:
        if not _effective_visible(later, visibility_override):
            continue
        r = _control_like_rect(nodes, later.name)
        if not r:
            continue
        if _rects_overlap(trect, r):
            notes.append(f"同父节点下后续控件 `{later.name}`（{later.type_name}）与按钮区域相交，可能被遮挡（未解析 z_index）")
    return notes


def summarize_control_interaction(
    nodes: list[ParsedNode],
    control_name: str,
    *,
    viewport: tuple[int, int],
    visibility_override: dict[str, bool] | None = None,
    force_external_instance_hidden: bool = False,
) -> dict[str, Any]:
    notes: list[str] = []
    if force_external_instance_hidden:
        notes.append("主场景脚本在 _ready 将容纳此 PackedScene 的实例节点设为 visible=false，启动时整段 UI 不可见")
        return {
            "ancestor_visible": False,
            "tree_visible": False,
            "receives_mouse": True,
            "effectively_invisible": False,
            "rect_in_viewport": True,
            "player_click_likelihood": "none",
            "automation_notes": notes,
            "runtime_visibility_source": "parent_scene_ready",
        }

    chain = ancestor_chain(nodes, control_name)
    target = nodes_by_name(nodes).get(control_name)
    ancestor_visible = True
    if len(chain) > 1:
        ancestor_visible = all(_effective_visible(n, visibility_override) for n in chain[1:])
    tree_visible = all(_effective_visible(n, visibility_override) for n in chain) if chain else True

    receives_mouse = True
    effectively_invisible = False
    if target:
        mf = _parse_mouse_filter(target)
        if mf == 2:
            receives_mouse = False
            notes.append("mouse_filter=IGNORE")
        mod = target.raw_attrs.get("modulate", "")
        if mod:
            alpha = _modulate_alpha(mod)
            if alpha is not None and alpha <= 0.001:
                effectively_invisible = True
                notes.append("modulate alpha ~0")

    notes.extend(_later_sibling_occlusion_notes(nodes, control_name, visibility_override=visibility_override))

    rect = control_screen_rect(nodes, control_name, viewport=viewport)
    vw, vh = viewport
    rect_in_viewport = False
    if rect:
        x, y, w, h = rect
        rect_in_viewport = w > 1 and h > 1 and x + w >= 0 and y + h >= 0 and x <= vw and y <= vh

    likelihood = "medium"
    if not tree_visible or not receives_mouse or effectively_invisible:
        likelihood = "none"
    elif not ancestor_visible:
        likelihood = "none"
    elif not rect_in_viewport:
        likelihood = "low"

    src = "tscn"
    if visibility_override:
        src = "tscn+script_ready"

    return {
        "ancestor_visible": ancestor_visible,
        "tree_visible": tree_visible,
        "receives_mouse": receives_mouse,
        "effectively_invisible": effectively_invisible,
        "rect_in_viewport": rect_in_viewport,
        "player_click_likelihood": likelihood,
        "automation_notes": notes,
        "runtime_visibility_source": src,
    }


def analyze_scene_buttons(
    project_root: Path,
    scene_rel: str,
    viewport: tuple[int, int],
    *,
    external_instance_root_hidden: bool = False,
) -> dict[str, Any]:
    path = project_root / scene_rel
    if not path.exists():
        return {"scene": scene_rel, "error": "missing_file", "buttons": {}}
    text = path.read_text(encoding="utf-8", errors="replace")
    nodes = parse_tscn_nodes(text)
    gd_rels = collect_gd_script_paths_from_tscn(project_root, text)
    gd_texts = []
    for rel in gd_rels:
        gp = project_root / rel
        if gp.is_file():
            gd_texts.append(gp.read_text(encoding="utf-8", errors="replace"))
    vis_override = apply_script_visibility_overrides(nodes, gd_texts, parse_visible_fn=_parse_visible)
    buttons: dict[str, Any] = {}
    for n in nodes:
        if "Button" not in n.type_name:
            continue
        buttons[n.name] = summarize_control_interaction(
            nodes,
            n.name,
            viewport=viewport,
            visibility_override=vis_override,
            force_external_instance_hidden=external_instance_root_hidden,
        )
    return {"scene": scene_rel, "buttons": buttons}
