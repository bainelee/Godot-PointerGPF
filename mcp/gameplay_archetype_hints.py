"""Static gameplay archetype hints and verb crosswalk (no network)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ARCHETYPES: list[dict[str, Any]] = [
    {
        "id": "first_person",
        "match": {
            "scene_types_any": ["CharacterBody3D", "Camera3D"],
            "method_tokens_any": ["shoot", "fire", "weapon", "_input", "is_on_floor"],
        },
        "typical_verbs": [
            {"verb": "move", "usual_effect": "改变角色位置"},
            {"verb": "look", "usual_effect": "改变视角朝向"},
            {"verb": "shoot", "usual_effect": "发射命中/消耗弹药等"},
        ],
    },
    {
        "id": "menu_driven",
        "match": {"keywords_any": ["ui-heavy"]},
        "typical_verbs": [
            {"verb": "navigate_ui", "usual_effect": "切换面板或弹窗"},
            {"verb": "confirm", "usual_effect": "提交选择或进入下一流程"},
        ],
    },
]


def read_inputmap_section(project_root: Path) -> str:
    path = project_root / "project.godot"
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\[input\](.*?)(?=^\[|\Z)", raw, flags=re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _archetype_matches(
    arch: dict[str, Any],
    scene_roots: set[str],
    method_blob: str,
    keywords: set[str],
) -> bool:
    m = arch.get("match") or {}
    st = m.get("scene_types_any")
    if st:
        if not scene_roots.intersection(set(st)):
            return False
    mt = m.get("method_tokens_any")
    if mt:
        if not any(tok.lower() in method_blob for tok in mt):
            return False
    kw_any = m.get("keywords_any")
    if kw_any:
        if not keywords.intersection(set(kw_any)):
            return False
    return True


def _verb_support(verb: str, method_blob: str, input_blob: str, keywords: set[str]) -> str:
    if verb == "shoot":
        return "has" if any(t in method_blob for t in ("shoot", "fire", "weapon")) else "weak"
    if verb == "move":
        return "has" if any(t in input_blob for t in ("ui_left", "ui_right", "move_left", "move_right")) else "weak"
    if verb == "look":
        return "has" if "mouse" in input_blob or "camera" in method_blob else "weak"
    if verb == "navigate_ui":
        return "has" if "ui-heavy" in keywords else "weak"
    if verb == "confirm":
        return "has" if "ui_accept" in input_blob or "ui-heavy" in keywords else "weak"
    return "weak"


def build_gameplay_understanding(
    *,
    inferred_keywords: list[str],
    script_method_blob: str,
    scene_root_types: list[str],
    inputmap_blob: str,
) -> dict[str, Any]:
    keywords = set(inferred_keywords)
    method_blob = script_method_blob.lower()
    input_blob = inputmap_blob.lower()
    scene_roots = set(scene_root_types)

    matched: list[str] = []
    for arch in ARCHETYPES:
        if _archetype_matches(arch, scene_roots, method_blob, keywords):
            matched.append(str(arch["id"]))

    verb_map: dict[str, dict[str, Any]] = {}
    for arch in ARCHETYPES:
        if str(arch["id"]) not in matched:
            continue
        for tv in arch.get("typical_verbs", []):
            verb = str(tv["verb"])
            sup = _verb_support(verb, method_blob, input_blob, keywords)
            prev = verb_map.get(verb)
            rank = {"absent": 0, "weak": 1, "has": 2}
            if prev is None or rank[sup] > rank.get(str(prev.get("support")), 0):
                verb_map[verb] = {
                    "verb": verb,
                    "usual_effect": tv.get("usual_effect", ""),
                    "support": sup,
                    "from_archetype": arch["id"],
                }

    return {
        "matched_archetypes": matched,
        "project_verbs": list(verb_map.values()),
        "disclaimer": "静态推断；以运行与设计文档为准。",
    }


def build_gameplay_understanding_for_project(
    project_root: Path,
    *,
    inferred_keywords: list[str],
    script_method_blob: str,
    scene_root_types: list[str],
) -> dict[str, Any]:
    blob = read_inputmap_section(project_root)
    return build_gameplay_understanding(
        inferred_keywords=inferred_keywords,
        script_method_blob=script_method_blob,
        scene_root_types=scene_root_types,
        inputmap_blob=blob,
    )
