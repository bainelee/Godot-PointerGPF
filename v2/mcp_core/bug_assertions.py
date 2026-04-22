from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .basicflow_assets import BasicFlowAssetError, load_basicflow_assets
from .bug_analysis import analyze_bug_report


def _scene_root_name(scene_path: str) -> str:
    stem = Path(str(scene_path or "").replace("res://", "")).stem
    if not stem:
        return ""
    return "".join(part.capitalize() for part in stem.split("_"))


def _extract_basicflow_hints(project_root: Path) -> list[str]:
    try:
        assets = load_basicflow_assets(project_root)
    except BasicFlowAssetError:
        return []
    hints: list[str] = []
    steps = assets.get("flow", {}).get("steps", [])
    if not isinstance(steps, list):
        return []
    for step in steps:
        if not isinstance(step, dict):
            continue
        hint = ""
        if isinstance(step.get("until"), dict):
            hint = str(step["until"].get("hint", "")).strip()
        if not hint:
            hint = str(step.get("hint", "")).strip()
        if hint and hint not in hints:
            hints.append(hint)
    return hints


def _find_target_scene(analysis: dict[str, Any]) -> str:
    location_scene = str(analysis.get("bug_intake", {}).get("location_hint", {}).get("scene", "")).strip()
    scenes = analysis.get("affected_artifacts", {}).get("scenes", [])
    if not isinstance(scenes, list):
        return ""
    preferred = [scene for scene in scenes if isinstance(scene, str) and scene and scene != location_scene]
    for keyword in ("game", "level", "hud", "pointer"):
        for scene in preferred:
            if keyword in scene.lower():
                return scene
    return preferred[0] if preferred else ""


def _assertion(
    assertion_id: str,
    *,
    kind: str,
    target: dict[str, Any],
    reason: str,
    hint: str,
    action: str = "check",
) -> dict[str, Any]:
    return {
        "id": assertion_id,
        "kind": kind,
        "target": target,
        "operator": "equals",
        "expected": True,
        "reason": reason,
        "runtime_check": {
            "supported": bool(hint),
            "hint": hint,
            "action": action,
        },
    }


def define_bug_assertions(project_root: Path, args: Any) -> dict[str, Any]:
    analysis = analyze_bug_report(project_root, args)
    intake = analysis.get("bug_intake", {})
    location_hint = intake.get("location_hint", {})
    location_node = str(location_hint.get("node", "")).strip()
    expected_behavior = str(intake.get("expected_behavior", "")).strip()
    basicflow_hints = _extract_basicflow_hints(project_root)

    preconditions: list[dict[str, Any]] = []
    postconditions: list[dict[str, Any]] = []

    precondition_hint = ""
    if location_node:
        for hint in basicflow_hints:
            if hint.startswith("node_exists:") and location_node.lower() in hint.lower():
                precondition_hint = hint
                break
        if not precondition_hint:
            precondition_hint = f"node_exists:{location_node}"
        preconditions.append(
            _assertion(
                "interaction_target_present",
                kind="runtime_hint",
                target={"hint": precondition_hint},
                reason=f"the interaction target {location_node} should exist before the trigger step",
                hint=precondition_hint,
            )
        )

    target_scene = _find_target_scene(analysis)
    target_scene_root = _scene_root_name(target_scene)
    if target_scene and target_scene_root:
        postconditions.append(
            _assertion(
                "target_scene_reached",
                kind="scene_active",
                target={"scene": target_scene},
                reason=expected_behavior or "the expected bug-free result should reach the target gameplay scene",
                hint=f"node_exists:{target_scene_root}",
                action="wait",
            )
        )

    if location_node:
        postconditions.append(
            _assertion(
                "interaction_target_hidden_after_success",
                kind="runtime_hint",
                target={"hint": f"node_hidden:{location_node}"},
                reason=f"the interaction target {location_node} should no longer stay visible after the bug-free transition",
                hint=f"node_hidden:{location_node}",
            )
        )

    return {
        "schema": "pointer_gpf.v2.assertion_set.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": analysis.get("bug_summary", ""),
        "bug_analysis": analysis,
        "preconditions": preconditions,
        "postconditions": postconditions,
        "assertions": [*preconditions, *postconditions],
    }
