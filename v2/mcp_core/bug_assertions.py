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


def _add_assertion(assertions: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    if any(existing.get("id") == payload.get("id") for existing in assertions):
        return
    assertions.append(payload)


def define_bug_assertions(project_root: Path, args: Any) -> dict[str, Any]:
    analysis = analyze_bug_report(project_root, args)
    intake = analysis.get("bug_intake", {})
    location_hint = intake.get("location_hint", {})
    location_node = str(location_hint.get("node", "")).strip()
    location_scene = str(location_hint.get("scene", "")).strip()
    expected_behavior = str(intake.get("expected_behavior", "")).strip()
    basicflow_hints = _extract_basicflow_hints(project_root)
    assertions: list[dict[str, Any]] = []

    target_scene = _find_target_scene(analysis)
    target_scene_root = _scene_root_name(target_scene)
    if target_scene:
        runtime_hint = f"node_exists:{target_scene_root}" if target_scene_root else ""
        _add_assertion(
            assertions,
            {
                "id": "target_scene_reached",
                "kind": "scene_active",
                "target": {"scene": target_scene},
                "operator": "equals",
                "expected": True,
                "reason": expected_behavior or "the expected bug-free result should reach the target gameplay scene",
                "runtime_check": {
                    "supported": bool(runtime_hint),
                    "hint": runtime_hint,
                    "action": "check",
                },
            },
        )

    for hint in basicflow_hints:
        if hint.startswith("node_exists:") and location_node and location_node.lower() in hint.lower():
            _add_assertion(
                assertions,
                {
                    "id": "interaction_target_present",
                    "kind": "runtime_hint",
                    "target": {"hint": hint},
                    "operator": "equals",
                    "expected": True,
                    "reason": f"the interaction target {location_node} should exist before the trigger step",
                    "runtime_check": {
                        "supported": True,
                        "hint": hint,
                        "action": "check",
                    },
                },
            )

    for hint in basicflow_hints:
        if hint.startswith("node_exists:") and target_scene_root and target_scene_root.lower() in hint.lower():
            _add_assertion(
                assertions,
                {
                    "id": "target_runtime_anchor_present",
                    "kind": "runtime_hint",
                    "target": {"hint": hint},
                    "operator": "equals",
                    "expected": True,
                    "reason": "the target runtime anchor should appear when the bug-free state is reached",
                    "runtime_check": {
                        "supported": True,
                        "hint": hint,
                        "action": "check",
                    },
                },
            )
    if not any(item.get("id") == "target_runtime_anchor_present" for item in assertions):
        for hint in basicflow_hints:
            if hint.startswith("node_exists:") and hint not in {item.get("runtime_check", {}).get("hint", "") for item in assertions}:
                _add_assertion(
                    assertions,
                    {
                        "id": "bug_free_runtime_anchor_present",
                        "kind": "runtime_hint",
                        "target": {"hint": hint},
                        "operator": "equals",
                        "expected": True,
                        "reason": "the bug-free state should expose at least one known runtime anchor from the project basicflow",
                        "runtime_check": {
                            "supported": True,
                            "hint": hint,
                            "action": "check",
                        },
                    },
                )
                break

    if location_node:
        _add_assertion(
            assertions,
            {
                "id": "interaction_should_change_state",
                "kind": "state_transition_required",
                "target": {
                    "node": location_node,
                    "scene": location_scene,
                },
                "operator": "changes_state",
                "expected": True,
                "reason": f"interacting with {location_node} should cause an observable state change in the bug-free case",
                "runtime_check": {
                    "supported": False,
                    "hint": "",
                    "action": "",
                },
            },
        )

    return {
        "schema": "pointer_gpf.v2.assertion_set.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": analysis.get("bug_summary", ""),
        "bug_analysis": analysis,
        "assertions": assertions,
    }
