from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .basicflow_assets import BasicFlowAssetError, load_basicflow_assets
from .bug_assertions import define_bug_assertions
from .bug_fix_verification import bug_fix_verification_path
from .bug_repro_execution import load_repro_result, repro_result_path

_MAIN_SCENE_RE = re.compile(r'^run/main_scene="(?P<path>res://[^"]+)"$', re.MULTILINE)
_FUNC_RE = re.compile(r"(?m)^\s*func\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
_NODE_RE = re.compile(r'(?m)^\[node\s+name="(?P<name>[^"]+)"(?P<body>[^\]]*)\]')
_TYPE_RE = re.compile(r'type="(?P<type>[^"]+)"')
_GROUPS_RE = re.compile(r"groups=\[(?P<groups>[^\]]+)\]")
_EXT_RESOURCE_RE = re.compile(r'(?m)^\[ext_resource[^\]]*path="(?P<path>res://[^"]+)"[^\]]*\]')
_CONNECTION_RE = re.compile(
    r'(?m)^\[connection[^\]]*signal="(?P<signal>[^"]+)"[^\]]*from="(?P<from>[^"]+)"[^\]]*to="(?P<to>[^"]+)"[^\]]*method="(?P<method>[^"]+)"[^\]]*\]'
)
_RES_REF_RE = re.compile(r'"(?P<path>res://[^"]+\.(?:gd|tscn|tres|res|material|shader))"')

_BEHAVIOR_METHOD_KEYWORDS = (
    "hit",
    "hurt",
    "damage",
    "flash",
    "feedback",
    "effect",
    "apply",
    "sync",
    "animation",
    "shader",
    "signal",
)
_VISUAL_STATE_KEYWORDS = (
    "modulate",
    "self_modulate",
    "material",
    "shader",
    "shader_parameter",
    "AnimationPlayer",
    "Tween",
    "Sprite2D",
    "Sprite3D",
    "Color",
    "hit_count",
    "hit_times",
    "hit_uvs",
)
_BUG_TEXT_KEYWORDS = {
    "敌人": "enemy",
    "受击": "hit",
    "击中": "hit",
    "闪红": "flash",
    "闪烁": "flash",
    "红色": "red",
    "动画": "animation",
    "材质": "material",
    "shader": "shader",
}
_IGNORED_PROJECT_PARTS = {"addons", "pointer_gpf", ".godot", ".git"}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _runtime_diagnostics_path(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp" / "runtime_diagnostics.json").resolve()


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


def _basicflow_summary(project_root: Path) -> dict[str, Any]:
    try:
        assets = load_basicflow_assets(project_root)
    except BasicFlowAssetError:
        return {
            "exists": False,
            "flow_file": "",
            "step_count": 0,
            "related_files": [],
            "runtime_hints": [],
        }
    flow = assets.get("flow", {})
    meta = assets.get("meta", {})
    steps = flow.get("steps", []) if isinstance(flow, dict) else []
    hints: list[dict[str, str]] = []
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            hint = ""
            if isinstance(step.get("until"), dict):
                hint = str(step["until"].get("hint", "")).strip()
            if not hint:
                hint = str(step.get("hint", "")).strip()
            if not hint and isinstance(step.get("target"), dict):
                hint = str(step["target"].get("hint", "")).strip()
            if hint:
                hints.append(
                    {
                        "step_id": str(step.get("id", "")).strip(),
                        "action": str(step.get("action", "")).strip(),
                        "hint": hint,
                    }
                )
    related_files = meta.get("related_files", []) if isinstance(meta, dict) else []
    return {
        "exists": True,
        "flow_file": str((project_root / "pointer_gpf" / "basicflow.json").resolve()),
        "step_count": len(steps) if isinstance(steps, list) else 0,
        "related_files": [str(item).strip() for item in related_files if str(item).strip()][:8],
        "runtime_hints": hints[:10],
    }


def _runtime_diagnostics_summary(project_root: Path) -> dict[str, Any]:
    path = _runtime_diagnostics_path(project_root)
    payload = _read_json(path)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []
    summaries: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summaries.append(
            {
                "kind": str(item.get("kind", "")).strip(),
                "message": str(item.get("message", "")).strip(),
            }
        )
    severity = str(payload.get("severity", "")).strip()
    blocking = [
        item
        for item in summaries
        if item["kind"].lower() in {"engine_log_error", "bridge_error"}
        and "acknowledged" not in item["message"].lower()
    ]
    return {
        "exists": path.is_file(),
        "path": str(path),
        "severity": severity,
        "item_count": len(summaries),
        "blocking_count": len(blocking),
        "items": summaries[:5],
        "blocking_items": blocking[:3],
    }


def _latest_repro_summary(project_root: Path) -> dict[str, Any]:
    payload = load_repro_result(project_root)
    artifact_path = str(repro_result_path(project_root))
    if not payload:
        return {
            "exists": False,
            "status": "",
            "failed_phase": "",
            "next_action": "",
            "artifact_file": artifact_path,
        }
    raw_error = payload.get("raw_run_result", {}).get("error", {}) if isinstance(payload.get("raw_run_result", {}), dict) else {}
    details = raw_error.get("details", {}) if isinstance(raw_error, dict) else {}
    if not isinstance(details, dict):
        details = {}
    return {
        "exists": True,
        "status": str(payload.get("status", "")).strip(),
        "failed_phase": str(payload.get("failed_phase", "")).strip(),
        "next_action": str(payload.get("next_action", "")).strip(),
        "artifact_file": str(payload.get("artifact_file", "")).strip() or artifact_path,
        "step_id": str(details.get("step_id", "")).strip(),
        "blocking_point": str(payload.get("blocking_point", "")).strip(),
        "check_summary": payload.get("check_summary", {}) if isinstance(payload.get("check_summary", {}), dict) else {},
        "runtime_evidence_summary": payload.get("runtime_evidence_summary", {})
        if isinstance(payload.get("runtime_evidence_summary", {}), dict)
        else {},
    }


def _latest_fix_verification_summary(project_root: Path) -> dict[str, Any]:
    path = bug_fix_verification_path(project_root)
    payload = _read_json(path)
    if not payload:
        return {
            "exists": False,
            "status": "",
            "reason": "",
            "artifact_file": str(path),
        }
    return {
        "exists": True,
        "status": str(payload.get("status", "")).strip(),
        "reason": str(payload.get("reason", "")).strip(),
        "artifact_file": str(path),
        "round_id": str(payload.get("round_id", "")).strip(),
        "bug_id": str(payload.get("bug_id", "")).strip(),
    }


def _candidate_file_read_order(assertion_set: dict[str, Any], basicflow_summary: dict[str, Any]) -> list[str]:
    bug_analysis = assertion_set.get("bug_analysis", {})
    artifacts = bug_analysis.get("affected_artifacts", {}) if isinstance(bug_analysis, dict) else {}
    scripts = artifacts.get("scripts", []) if isinstance(artifacts, dict) else []
    scenes = artifacts.get("scenes", []) if isinstance(artifacts, dict) else []
    related_files = basicflow_summary.get("related_files", [])
    candidates: list[str] = []
    for group in (scripts, scenes, related_files):
        if not isinstance(group, list):
            continue
        for item in group:
            value = str(item).strip()
            if value and value not in candidates:
                candidates.append(value)
    return candidates[:10]


def _res_to_path(project_root: Path, res_path: str) -> Path:
    relative = str(res_path or "").strip().replace("res://", "").replace("/", "\\")
    return (project_root / relative).resolve()


def _path_to_res(project_root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return ""
    return "res://" + relative.as_posix()


def _read_text(path: Path, max_chars: int = 120_000) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
    except OSError:
        return ""
    return text[:max_chars]


def _project_files(project_root: Path) -> list[Path]:
    out: list[Path] = []
    for suffix in ("*.gd", "*.tscn", "*.tres"):
        for path in project_root.rglob(suffix):
            parts = set(path.relative_to(project_root).parts)
            if parts.intersection(_IGNORED_PROJECT_PARTS):
                continue
            out.append(path.resolve())
    return sorted(set(out), key=lambda item: str(item).lower())


def _bug_tokens(bug_intake: dict[str, Any]) -> set[str]:
    location_hint = bug_intake.get("location_hint", {}) if isinstance(bug_intake.get("location_hint", {}), dict) else {}
    raw_parts = [
        bug_intake.get("summary", ""),
        bug_intake.get("observed_behavior", ""),
        bug_intake.get("expected_behavior", ""),
        " ".join(bug_intake.get("steps_to_trigger", [])) if isinstance(bug_intake.get("steps_to_trigger", []), list) else "",
        location_hint.get("node", ""),
        location_hint.get("scene", ""),
        location_hint.get("script", ""),
    ]
    raw = " ".join(str(item) for item in raw_parts).lower()
    tokens = {value.lower() for value in re.findall(r"[A-Za-z][A-Za-z0-9_]+", raw)}
    for cn, token in _BUG_TEXT_KEYWORDS.items():
        if cn in raw:
            tokens.add(token)
    if "enemy" in tokens:
        tokens.update({"enemy", "enemies", "testenemy"})
    if "hit" in tokens:
        tokens.update({"hit", "damage", "hurt", "bullet"})
    if "flash" in tokens:
        tokens.update({"flash", "red", "feedback", "shader", "material", "modulate"})
    return {token for token in tokens if len(token) >= 3}


def _extract_res_refs(text: str) -> list[str]:
    refs: list[str] = []
    for pattern in (_EXT_RESOURCE_RE, _RES_REF_RE):
        for match in pattern.finditer(text):
            value = str(match.group("path")).strip()
            if value and value not in refs:
                refs.append(value)
    return refs


def _seed_static_files(
    project_root: Path,
    startup_scene: str,
    candidate_files: list[str],
    bug_intake: dict[str, Any],
) -> list[Path]:
    selected: list[Path] = []

    def add_res(res_path: str) -> None:
        value = str(res_path or "").strip()
        if not value.startswith("res://"):
            return
        path = _res_to_path(project_root, value)
        if path.is_file() and path not in selected:
            selected.append(path)

    add_res(startup_scene)
    for item in candidate_files:
        add_res(item)
    location_hint = bug_intake.get("location_hint", {}) if isinstance(bug_intake.get("location_hint", {}), dict) else {}
    add_res(str(location_hint.get("scene", "")).strip())
    add_res(str(location_hint.get("script", "")).strip())

    tokens = _bug_tokens(bug_intake)
    for path in _project_files(project_root):
        res_path = _path_to_res(project_root, path).lower()
        text = _read_text(path, max_chars=40_000).lower()
        if any(token in res_path or token in text for token in tokens):
            if path not in selected:
                selected.append(path)

    # Follow first-level resource references from selected scenes and scripts.
    for path in list(selected):
        text = _read_text(path)
        for ref in _extract_res_refs(text):
            ref_path = _res_to_path(project_root, ref)
            if ref_path.is_file() and ref_path not in selected:
                selected.append(ref_path)
    return selected[:24]


def _score_reasons(res_path: str, text: str, tokens: set[str], forced: bool) -> list[str]:
    reasons: list[str] = []
    lower_path = res_path.lower()
    lower_text = text.lower()
    if forced:
        reasons.append("referenced_by_bug_or_basicflow")
    matched_tokens = [token for token in sorted(tokens) if token in lower_path or token in lower_text]
    if matched_tokens:
        reasons.append("matches_bug_terms:" + ",".join(matched_tokens[:4]))
    if any(keyword.lower() in lower_text for keyword in _VISUAL_STATE_KEYWORDS):
        reasons.append("contains_visual_state_terms")
    if any(keyword in lower_text for keyword in ("signal", "connect", "[connection")):
        reasons.append("contains_signal_terms")
    return reasons[:4]


def _groups_from_node_body(body: str) -> list[str]:
    match = _GROUPS_RE.search(body)
    if not match:
        return []
    raw = match.group("groups")
    return [item.strip().strip('"') for item in raw.split(",") if item.strip().strip('"')]


def _script_methods(res_path: str, text: str) -> list[dict[str, str]]:
    methods: list[dict[str, str]] = []
    for match in _FUNC_RE.finditer(text):
        name = match.group("name")
        lower = name.lower()
        if any(keyword in lower for keyword in _BEHAVIOR_METHOD_KEYWORDS):
            methods.append(
                {
                    "script": res_path,
                    "method": name,
                    "reason": "method name suggests behavior, feedback, hit, animation, or shader logic",
                }
            )
    return methods[:12]


def _scene_nodes(res_path: str, text: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for match in _NODE_RE.finditer(text):
        body = match.group("body")
        type_match = _TYPE_RE.search(body)
        node_type = type_match.group("type") if type_match else ""
        name = match.group("name")
        if node_type in {"AnimationPlayer", "Sprite2D", "Sprite3D", "CanvasItem", "MeshInstance3D"} or any(
            token in name.lower() for token in ("enemy", "hit", "flash", "feedback", "sprite")
        ):
            nodes.append(
                {
                    "scene": res_path,
                    "node": name,
                    "type": node_type,
                    "groups": _groups_from_node_body(body),
                }
            )
    return nodes[:16]


def _signal_connections(res_path: str, text: str) -> list[dict[str, str]]:
    connections: list[dict[str, str]] = []
    for match in _CONNECTION_RE.finditer(text):
        connections.append(
            {
                "scene": res_path,
                "signal": match.group("signal"),
                "from": match.group("from"),
                "to": match.group("to"),
                "method": match.group("method"),
            }
        )
    return connections[:12]


def _visual_surfaces(res_path: str, text: str) -> list[dict[str, str]]:
    surfaces: list[dict[str, str]] = []
    lower = text.lower()
    keyword_map = {
        "modulate": "node_property",
        "self_modulate": "node_property",
        "shader_parameter": "shader_param",
        "set_shader_parameter": "shader_param",
        "hit_count": "shader_param",
        "hit_times": "shader_param",
        "hit_uvs": "shader_param",
        "AnimationPlayer": "animation_state",
        "tween": "node_property",
        "material": "shader_or_material",
    }
    for keyword, kind in keyword_map.items():
        if keyword.lower() in lower:
            surfaces.append(
                {
                    "file": res_path,
                    "kind": kind,
                    "term": keyword,
                }
            )
    return surfaces[:12]


def _runtime_target_candidates(
    nodes: list[dict[str, Any]],
    methods: list[dict[str, str]],
    surfaces: list[dict[str, str]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for node in nodes:
        node_name = str(node.get("node", "")).strip()
        node_type = str(node.get("type", "")).strip()
        if not node_name:
            continue
        if node_type in {"Sprite2D", "Sprite3D"}:
            candidates.append(
                {
                    "target": {"hint": f"node_name:{node_name}"},
                    "action": "sample",
                    "metric": {"kind": "node_property", "property_path": "modulate"},
                    "reason": "sprite-like node can expose visible color or material state",
                }
            )
        if node_type == "AnimationPlayer":
            candidates.append(
                {
                    "target": {"hint": f"node_name:{node_name}"},
                    "action": "sample",
                    "metric": {"kind": "animation_state"},
                    "reason": "AnimationPlayer can prove whether feedback animation played",
                }
            )
    if any(surface.get("kind") == "shader_param" for surface in surfaces):
        candidates.append(
            {
                "target": {"hint": "node_name:Sprite3D"},
                "action": "sample",
                "metric": {"kind": "shader_param", "param_name": "hit_count"},
                "reason": "shader hit_count is a generic hit-feedback evidence candidate when present",
            }
        )
    if any("signal" in method.get("method", "").lower() for method in methods):
        candidates.append(
            {
                "action": "observe",
                "event": {"kind": "signal_emitted"},
                "reason": "script methods mention signal behavior",
            }
        )
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:10]


def _project_static_observation(
    project_root: Path,
    startup_scene: str,
    candidate_files: list[str],
    bug_intake: dict[str, Any],
) -> dict[str, Any]:
    tokens = _bug_tokens(bug_intake)
    forced_res_paths = {item for item in [startup_scene, *candidate_files] if str(item).startswith("res://")}
    files = _seed_static_files(project_root, startup_scene, candidate_files, bug_intake)
    candidate_file_entries: list[dict[str, Any]] = []
    methods: list[dict[str, str]] = []
    nodes: list[dict[str, Any]] = []
    connections: list[dict[str, str]] = []
    surfaces: list[dict[str, str]] = []
    refs: list[dict[str, str]] = []

    for path in files:
        res_path = _path_to_res(project_root, path)
        if not res_path:
            continue
        text = _read_text(path)
        reasons = _score_reasons(res_path, text, tokens, res_path in forced_res_paths)
        candidate_file_entries.append(
            {
                "path": res_path,
                "kind": path.suffix.lstrip("."),
                "reasons": reasons,
            }
        )
        if path.suffix == ".gd":
            methods.extend(_script_methods(res_path, text))
        if path.suffix == ".tscn":
            nodes.extend(_scene_nodes(res_path, text))
            connections.extend(_signal_connections(res_path, text))
        surfaces.extend(_visual_surfaces(res_path, text))
        for ref in _extract_res_refs(text):
            refs.append({"from": res_path, "to": ref})

    runtime_targets = _runtime_target_candidates(nodes, methods, surfaces)
    return {
        "schema": "pointer_gpf.v2.project_static_observation.v1",
        "candidate_files": candidate_file_entries[:16],
        "candidate_nodes": nodes[:16],
        "candidate_scripts": methods[:16],
        "signal_connections": connections[:12],
        "visual_state_surfaces": surfaces[:16],
        "resource_references": refs[:20],
        "runtime_evidence_target_candidates": runtime_targets,
        "bug_term_tokens": sorted(tokens)[:16],
    }


def observe_bug_context(project_root: Path, args: Any) -> dict[str, Any]:
    assertion_set = define_bug_assertions(project_root, args)
    bug_analysis = assertion_set.get("bug_analysis", {})
    bug_intake = bug_analysis.get("bug_intake", {}) if isinstance(bug_analysis, dict) else {}
    basicflow_summary = _basicflow_summary(project_root)
    runtime_summary = _runtime_diagnostics_summary(project_root)
    repro_summary = _latest_repro_summary(project_root)
    verification_summary = _latest_fix_verification_summary(project_root)
    candidate_files = _candidate_file_read_order(assertion_set, basicflow_summary)
    startup_scene = _read_startup_scene(project_root)
    static_observation = _project_static_observation(project_root, startup_scene, candidate_files, bug_intake)
    return {
        "schema": "pointer_gpf.v2.bug_observation.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": assertion_set.get("bug_summary", ""),
        "startup_scene": startup_scene,
        "bug_intake": bug_intake,
        "bug_analysis": bug_analysis,
        "assertion_set": assertion_set,
        "basicflow_summary": basicflow_summary,
        "runtime_diagnostics": runtime_summary,
        "latest_repro_result": repro_summary,
        "runtime_evidence_capabilities": {
            "schema": "pointer_gpf.v2.runtime_evidence_capabilities.v1",
            "actions": ["sample", "observe", "callMethod", "check"],
            "record_types": ["read_result", "sample_result", "event_observer_result", "comparison_result"],
            "status": "contract_defined_python_side",
        },
        "latest_runtime_evidence_summary": repro_summary.get("runtime_evidence_summary", {})
        if isinstance(repro_summary.get("runtime_evidence_summary", {}), dict)
        else {},
        "latest_fix_verification": verification_summary,
        "candidate_file_read_order": candidate_files,
        "project_static_observation": static_observation,
        "investigation_focus": list(bug_analysis.get("recommended_assertion_focus", []))[:5] if isinstance(bug_analysis, dict) else [],
    }
