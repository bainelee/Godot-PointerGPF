from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .basicflow_assets import BasicFlowAssetError, load_basicflow_assets
from .bug_report import collect_bug_report

_MAIN_SCENE_RE = re.compile(r'^run/main_scene="(?P<path>res://[^"]+)"$', re.MULTILINE)


def _read_startup_scene(project_root: Path) -> str:
    project_file = project_root / "project.godot"
    if not project_file.is_file():
        return ""
    try:
        text = project_file.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = _MAIN_SCENE_RE.search(text)
    return str(match.group("path")).strip() if match else ""


def _basename_without_suffix(path_text: str) -> str:
    cleaned = str(path_text or "").strip()
    if not cleaned:
        return ""
    return Path(cleaned.replace("res://", "")).stem.lower()


def _normalize_res_path(path_text: str) -> str:
    cleaned = str(path_text or "").strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.startswith("res://") else cleaned


def _load_basicflow_context(project_root: Path) -> dict[str, Any]:
    try:
        return load_basicflow_assets(project_root)
    except BasicFlowAssetError:
        return {}


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    haystack = str(text or "").lower()
    return any(keyword in haystack for keyword in keywords)


def _pick_affected_artifacts(project_root: Path, intake: dict[str, Any], basicflow_assets: dict[str, Any]) -> dict[str, list[str]]:
    startup_scene = _read_startup_scene(project_root)
    location_hint = intake.get("location_hint", {})
    location_scene = _normalize_res_path(location_hint.get("scene", ""))
    location_script = _normalize_res_path(location_hint.get("script", ""))
    location_node = str(location_hint.get("node", "")).strip()
    observed = str(intake.get("observed_behavior", ""))
    expected = str(intake.get("expected_behavior", ""))
    summary = str(intake.get("summary", ""))

    related_files = []
    if isinstance(basicflow_assets.get("meta"), dict):
        meta_related_files = basicflow_assets["meta"].get("related_files", [])
        if isinstance(meta_related_files, list):
            related_files = [str(item).strip() for item in meta_related_files if str(item).strip()]

    token_candidates = {
        _basename_without_suffix(startup_scene),
        _basename_without_suffix(location_scene),
        _basename_without_suffix(location_script),
        _basename_without_suffix(summary),
        _basename_without_suffix(observed),
        _basename_without_suffix(expected),
        location_node.lower(),
    }
    token_candidates.discard("")

    scenes: list[str] = []
    scripts: list[str] = []
    nodes: list[str] = []

    def add_scene(value: str) -> None:
        normalized = _normalize_res_path(value)
        if normalized and normalized not in scenes:
            scenes.append(normalized)

    def add_script(value: str) -> None:
        normalized = _normalize_res_path(value)
        if normalized and normalized not in scripts:
            scripts.append(normalized)

    if startup_scene:
        add_scene(startup_scene)
    if location_scene:
        add_scene(location_scene)
    if location_script:
        add_script(location_script)
    if location_node:
        nodes.append(location_node)

    basicflow_flow_text = json.dumps(basicflow_assets.get("flow", {}), ensure_ascii=False) if basicflow_assets else ""

    for rel in related_files:
        rel_lower = rel.lower()
        if any(token and token in rel_lower for token in token_candidates):
            if rel_lower.endswith(".tscn"):
                add_scene(rel)
            if rel_lower.endswith(".gd"):
                add_script(rel)

    if location_node and location_node.lower() in basicflow_flow_text.lower():
        for rel in related_files:
            rel_lower = rel.lower()
            if rel_lower.endswith(".tscn"):
                add_scene(rel)
            if rel_lower.endswith(".gd"):
                add_script(rel)

    return {
        "scenes": scenes[:4],
        "nodes": nodes[:3],
        "scripts": scripts[:4],
    }


def _build_suspected_causes(intake: dict[str, Any], artifacts: dict[str, list[str]]) -> tuple[list[dict[str, str]], list[str]]:
    observed = str(intake.get("observed_behavior", ""))
    expected = str(intake.get("expected_behavior", ""))
    location_hint = intake.get("location_hint", {})
    location_node = str(location_hint.get("node", "")).strip()
    location_scene = str(location_hint.get("scene", "")).strip()
    scenes = artifacts.get("scenes", [])
    scripts = artifacts.get("scripts", [])

    causes: list[dict[str, str]] = []
    assertion_focus: list[str] = []

    if _contains_any(observed, ("没有反应", "无反应", "没反应", "no response", "does not respond")) and location_node:
        causes.append(
            {
                "kind": "button_signal_or_callback_broken",
                "confidence": "medium",
                "reason": f"bug action is centered on node {location_node} and the symptom is no response after interaction",
            }
        )
        assertion_focus.append("the target interaction should trigger a visible state change")

    if _contains_any(expected, ("进入", "切换", "scene", "关卡", "level", "transition")):
        target_scene = ""
        for scene in scenes:
            if scene != location_scene:
                target_scene = scene
                break
        causes.append(
            {
                "kind": "scene_transition_not_triggered",
                "confidence": "medium",
                "reason": "expected behavior describes entering another gameplay state or scene, so transition logic is a likely failure point",
            }
        )
        if target_scene:
            assertion_focus.append(f"scene transition should reach {target_scene}")
        assertion_focus.append("the current menu/start state should not remain active after the trigger")

    if scripts:
        causes.append(
            {
                "kind": "script_path_should_be_inspected",
                "confidence": "low",
                "reason": f"related script artifacts were identified: {', '.join(scripts[:2])}",
            }
        )

    if not causes:
        causes.append(
            {
                "kind": "affected_runtime_path_needs_inspection",
                "confidence": "low",
                "reason": "the bug report was normalized, but the symptom does not yet match a narrower heuristic bucket",
            }
        )
    if not assertion_focus:
        assertion_focus.append("the expected non-bug state should be turned into explicit observable assertions")
    return causes[:3], assertion_focus[:3]


def _build_evidence(project_root: Path, intake: dict[str, Any], artifacts: dict[str, list[str]], basicflow_assets: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    startup_scene = _read_startup_scene(project_root)
    if startup_scene:
        evidence.append(f"project startup scene is {startup_scene}")
    location_hint = intake.get("location_hint", {})
    if str(location_hint.get("node", "")).strip():
        evidence.append(f"bug intake location hint references node {location_hint['node']}")
    if str(location_hint.get("scene", "")).strip():
        evidence.append(f"bug intake location hint references scene {location_hint['scene']}")

    flow_payload = basicflow_assets.get("flow", {})
    if flow_payload:
        evidence.append("project-local basicflow assets exist and can help locate the affected path")
        flow_text = json.dumps(flow_payload, ensure_ascii=False)
        node_name = str(location_hint.get("node", "")).strip()
        if node_name and node_name.lower() in flow_text.lower():
            evidence.append(f"project basicflow already references node {node_name}")
    if artifacts.get("scripts"):
        evidence.append(f"related scripts were identified from project artifacts: {', '.join(artifacts['scripts'][:2])}")
    return evidence[:5]


def analyze_bug_report(project_root: Path, args: Any) -> dict[str, Any]:
    intake = collect_bug_report(project_root, args)
    basicflow_assets = _load_basicflow_context(project_root)
    artifacts = _pick_affected_artifacts(project_root, intake, basicflow_assets)
    suspected_causes, assertion_focus = _build_suspected_causes(intake, artifacts)
    evidence = _build_evidence(project_root, intake, artifacts, basicflow_assets)
    return {
        "schema": "pointer_gpf.v2.bug_analysis.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": intake["summary"],
        "bug_intake": intake,
        "suspected_causes": suspected_causes,
        "affected_artifacts": artifacts,
        "evidence": evidence,
        "recommended_assertion_focus": assertion_focus,
    }
