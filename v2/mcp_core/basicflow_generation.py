from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .basicflow_assets import (
    BasicFlowPaths,
    build_basicflow_metadata,
    compute_project_file_summary,
    save_basicflow_assets,
)


class BasicFlowGenerationError(ValueError):
    pass


def normalize_generation_answers(answers: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(answers, dict):
        raise BasicFlowGenerationError("generation answers must be an object")
    main_scene_is_entry = bool(answers.get("main_scene_is_entry", True))
    tested_features_raw = answers.get("tested_features", [])
    if isinstance(tested_features_raw, str):
        tested_features = [part.strip() for part in tested_features_raw.split(",")]
    elif isinstance(tested_features_raw, list):
        tested_features = [str(item) for item in tested_features_raw]
    else:
        raise BasicFlowGenerationError("tested_features must be a string or a list of strings")
    include_screenshot_evidence = bool(answers.get("include_screenshot_evidence", False))
    entry_scene_path = answers.get("entry_scene_path")
    if entry_scene_path is not None:
        entry_scene_path = str(entry_scene_path)
    return {
        "main_scene_is_entry": main_scene_is_entry,
        "tested_features": tested_features,
        "include_screenshot_evidence": include_screenshot_evidence,
        "entry_scene_path": entry_scene_path,
    }


def get_basicflow_generation_questions(project_root: Path) -> dict[str, Any]:
    startup_scene = _read_startup_scene(project_root.resolve())
    return {
        "status": "questions_ready",
        "question_count": 3,
        "questions": [
            {
                "id": "main_scene_is_entry",
                "question": "当前游戏工程的主场景是否是游戏主流程的入口？",
                "type": "boolean",
                "required": True,
                "default": True,
                "project_hint": startup_scene,
                "followup_field": "entry_scene_path",
                "followup_hint": "如不是，请补充真正入口场景路径",
            },
            {
                "id": "tested_features",
                "question": "你认为应该被测试的游戏功能都有哪些？",
                "type": "string_list",
                "required": True,
                "format_hint": "用逗号分隔，或传字符串数组",
            },
            {
                "id": "include_screenshot_evidence",
                "question": "测试是否需要保留截图证据？",
                "type": "boolean",
                "required": True,
                "default": False,
            },
        ],
        "answer_fields": [
            "main_scene_is_entry",
            "tested_features",
            "include_screenshot_evidence",
            "entry_scene_path",
        ],
    }


def generate_basicflow_assets(
    project_root: Path,
    *,
    main_scene_is_entry: bool,
    tested_features: list[str],
    include_screenshot_evidence: bool,
    entry_scene_path: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    normalized_features = [item.strip() for item in tested_features if isinstance(item, str) and item.strip()]
    if not normalized_features:
        raise BasicFlowGenerationError("tested_features must contain at least one non-empty item")
    startup_scene = _read_startup_scene(project_root)
    if not main_scene_is_entry and not (entry_scene_path or "").strip():
        raise BasicFlowGenerationError(
            "entry_scene_path is required when the startup scene is not the intended gameplay entry"
        )
    related_files = ["project.godot"]
    if startup_scene:
        related_files.append(startup_scene)
    normalized_entry_scene = (entry_scene_path or "").strip()
    if normalized_entry_scene and normalized_entry_scene not in related_files:
        related_files.append(normalized_entry_scene)
    detected_targets = _detect_project_specific_targets(project_root, startup_scene if main_scene_is_entry else normalized_entry_scene)
    for path in detected_targets.get("related_files", []):
        if path not in related_files:
            related_files.append(path)
    flow_payload = _build_basicflow_payload(
        feature_summary=normalized_features,
        include_screenshot_evidence=include_screenshot_evidence,
        detected_targets=detected_targets,
    )
    metadata = build_basicflow_metadata(
        generation_summary=_build_generation_summary(
            main_scene_is_entry=main_scene_is_entry,
            startup_scene=startup_scene,
            entry_scene_path=normalized_entry_scene,
            tested_features=normalized_features,
            include_screenshot_evidence=include_screenshot_evidence,
            detected_targets=detected_targets,
        ),
        related_files=related_files,
        project_file_summary=compute_project_file_summary(project_root),
    )
    paths = save_basicflow_assets(project_root, flow_payload, metadata)
    return {
        "paths": {"flow_file": str(paths.flow_file), "meta_file": str(paths.meta_file)},
        "flow": flow_payload,
        "meta": metadata,
    }


def load_generation_answers(answer_file: Path) -> dict[str, Any]:
    try:
        payload = json.loads(answer_file.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise BasicFlowGenerationError(f"generation answer file does not exist: {answer_file}") from exc
    except OSError as exc:
        raise BasicFlowGenerationError(f"could not read generation answer file: {answer_file}") from exc
    except json.JSONDecodeError as exc:
        raise BasicFlowGenerationError(f"generation answer file is not valid JSON: {answer_file}") from exc
    if not isinstance(payload, dict):
        raise BasicFlowGenerationError("generation answer file must contain an object")
    return payload


def generate_basicflow_from_answers_file(project_root: Path, answer_file: Path) -> dict[str, Any]:
    answers = load_generation_answers(answer_file)
    normalized = normalize_generation_answers(answers)
    return generate_basicflow_assets(
        project_root,
        main_scene_is_entry=bool(normalized["main_scene_is_entry"]),
        tested_features=list(normalized["tested_features"]),
        include_screenshot_evidence=bool(normalized["include_screenshot_evidence"]),
        entry_scene_path=str(normalized["entry_scene_path"]) if normalized["entry_scene_path"] is not None else None,
    )


def generate_basicflow_from_answers(project_root: Path, answers: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_generation_answers(answers)
    return generate_basicflow_assets(
        project_root,
        main_scene_is_entry=bool(normalized["main_scene_is_entry"]),
        tested_features=list(normalized["tested_features"]),
        include_screenshot_evidence=bool(normalized["include_screenshot_evidence"]),
        entry_scene_path=str(normalized["entry_scene_path"]) if normalized["entry_scene_path"] is not None else None,
    )


def _build_basicflow_payload(
    *,
    feature_summary: list[str],
    include_screenshot_evidence: bool,
    detected_targets: dict[str, Any],
) -> dict[str, Any]:
    mode = detected_targets.get("mode")
    start_button = str(detected_targets.get("start_button_name", "")).strip()
    target_root = str(detected_targets.get("target_scene_root_name", "")).strip()
    runtime_anchor = str(detected_targets.get("runtime_anchor_name", "")).strip()
    if mode in {"button_to_scene_with_runtime_anchor", "button_to_scene_root"} and start_button and target_root:
        check_hint = runtime_anchor or target_root
        check_step_id = (
            f"check_{_normalize_step_token(runtime_anchor)}"
            if runtime_anchor
            else f"check_{_normalize_step_token(target_root)}"
        )
        steps: list[dict[str, Any]] = [
            {"id": "launch_game", "action": "launchGame"},
            {
                "id": f"wait_{_normalize_step_token(start_button)}",
                "action": "wait",
                "until": {"hint": f"node_exists:{start_button}"},
                "timeoutMs": 5000,
            },
            {
                "id": f"click_{_normalize_step_token(start_button)}",
                "action": "click",
                "target": {"hint": f"node_name:{start_button}"},
            },
            {
                "id": f"wait_{_normalize_step_token(target_root)}",
                "action": "wait",
                "until": {"hint": f"node_exists:{target_root}"},
                "timeoutMs": 5000,
            },
            {"id": check_step_id, "action": "check", "hint": f"node_exists:{check_hint}"},
        ]
    else:
        steps = [
            {"id": "launch_game", "action": "launchGame"},
            {"id": "wait_runtime_ready", "action": "wait", "until": {"hint": "runtime_alive"}, "timeoutMs": 5000},
            {
                "id": "visible_click_probe",
                "action": "click",
                "target": {"x": 240, "y": 180},
            },
            {"id": "check_runtime_alive", "action": "check", "hint": "runtime_alive"},
        ]
    if include_screenshot_evidence:
        steps.append({"id": "capture_baseline", "action": "snapshot"})
    steps.append({"id": "close_project", "action": "closeProject"})
    return {
        "flowId": "project_basicflow",
        "name": "Project Basic Flow",
        "description": "Generated baseline flow covering: " + ", ".join(feature_summary),
        "steps": steps,
    }


def _build_generation_summary(
    *,
    main_scene_is_entry: bool,
    startup_scene: str,
    entry_scene_path: str,
    tested_features: list[str],
    include_screenshot_evidence: bool,
    detected_targets: dict[str, Any],
) -> str:
    target_entry = startup_scene if main_scene_is_entry else entry_scene_path
    evidence_text = "with screenshot evidence" if include_screenshot_evidence else "without screenshot evidence"
    target_mode = str(detected_targets.get("mode", "generic_runtime_probe"))
    return (
        "Generated basicflow for startup validation and baseline runtime assertion. "
        f"Target entry: {target_entry or 'unknown'}. "
        f"Detected target mode: {target_mode}. "
        f"User-requested features: {', '.join(tested_features)}. "
        f"Run mode: {evidence_text}."
    )


def _detect_project_specific_targets(project_root: Path, startup_scene: str) -> dict[str, Any]:
    related_files: list[str] = []
    startup_scene_path = _resolve_res_path(project_root, startup_scene)
    startup_text = _read_text_if_file(startup_scene_path)
    if startup_scene and startup_text:
        related_files.append(startup_scene)
    startup_resources = _parse_ext_resources(startup_text)
    start_scene_path = _detect_start_scene_path(project_root, startup_resources)
    start_button_name = ""
    if start_scene_path:
        start_button_name = _detect_preferred_button_name(project_root, start_scene_path)
        if start_scene_path not in related_files:
            related_files.append(start_scene_path)
    startup_script_path = _first_resource_path(startup_resources, resource_type="Script")
    target_scene_path = ""
    if startup_script_path:
        if startup_script_path not in related_files:
            related_files.append(startup_script_path)
        target_scene_path = _detect_scene_transition_target(project_root, startup_script_path)
    if not (start_button_name and target_scene_path):
        return {"mode": "generic_runtime_probe", "related_files": related_files}
    target_scene_text = _read_text_if_file(_resolve_res_path(project_root, target_scene_path))
    target_root_name = _parse_scene_root_name(target_scene_text)
    if not target_root_name:
        return {"mode": "generic_runtime_probe", "related_files": related_files}
    if target_scene_path not in related_files:
        related_files.append(target_scene_path)
    runtime_anchor_name = ""
    runtime_anchor_path = ""
    target_resources = _parse_ext_resources(target_scene_text)
    target_script_path = _first_resource_path(target_resources, resource_type="Script")
    if target_script_path:
        if target_script_path not in related_files:
            related_files.append(target_script_path)
        runtime_anchor_path = _detect_runtime_anchor_scene_path(project_root, target_scene_path, target_script_path)
    if not runtime_anchor_path:
        runtime_anchor_path = _detect_runtime_anchor_scene_path(project_root, target_scene_path, "")
    if runtime_anchor_path:
        runtime_anchor_text = _read_text_if_file(_resolve_res_path(project_root, runtime_anchor_path))
        runtime_anchor_name = _parse_scene_root_name(runtime_anchor_text)
        if runtime_anchor_name and runtime_anchor_path not in related_files:
            related_files.append(runtime_anchor_path)
    if runtime_anchor_name:
        return {
            "mode": "button_to_scene_with_runtime_anchor",
            "related_files": related_files,
            "start_button_name": start_button_name,
            "target_scene_path": target_scene_path,
            "target_scene_root_name": target_root_name,
            "runtime_anchor_name": runtime_anchor_name,
        }
    return {
        "mode": "button_to_scene_root",
        "related_files": related_files,
        "start_button_name": start_button_name,
        "target_scene_path": target_scene_path,
        "target_scene_root_name": target_root_name,
    }
    
    
def _normalize_step_token(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return normalized.strip("_") or "target"


def _read_text_if_file(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _parse_ext_resources(scene_text: str) -> list[dict[str, str]]:
    resources: list[dict[str, str]] = []
    for attrs in re.findall(r"\[ext_resource\s+([^\]]+)\]", scene_text):
        type_match = re.search(r'type="(?P<type>[^"]+)"', attrs)
        path_match = re.search(r'path="(?P<path>res://[^"]+)"', attrs)
        if type_match and path_match:
            resources.append({"type": type_match.group("type"), "path": path_match.group("path")})
    return resources


def _first_resource_path(resources: list[dict[str, str]], *, resource_type: str) -> str:
    for item in resources:
        if item.get("type") == resource_type:
            return str(item.get("path", "")).strip()
    return ""


def _detect_start_scene_path(project_root: Path, resources: list[dict[str, str]]) -> str:
    candidates = [item.get("path", "") for item in resources if item.get("type") == "PackedScene"]
    preferred_keywords = ("start", "menu", "title", "intro")
    for path in candidates:
        lowered = str(path).lower()
        if not any(keyword in lowered for keyword in preferred_keywords):
            continue
        if _detect_preferred_button_name(project_root, str(path)):
            return str(path)
    for path in candidates:
        if _detect_preferred_button_name(project_root, str(path)):
            return str(path)
    return ""


def _detect_preferred_button_name(project_root: Path, scene_path: str) -> str:
    scene_text = _read_text_if_file(_resolve_res_path(project_root, scene_path))
    if not scene_text:
        return ""
    buttons = re.findall(r'\[node name="([^"]+)" type="Button"', scene_text)
    if not buttons:
        return ""
    preferred_keywords = ("start", "play", "begin", "enter", "continue")
    for name in buttons:
        lowered = name.lower()
        if any(keyword in lowered for keyword in preferred_keywords):
            return name
    return buttons[0]


def _detect_scene_transition_target(project_root: Path, script_path: str) -> str:
    script_text = _read_text_if_file(_resolve_res_path(project_root, script_path))
    if not script_text:
        return ""
    direct_match = re.search(r'change_scene_to_file\(\s*"(?P<path>res://[^"]+\.tscn)"\s*\)', script_text)
    if direct_match:
        return direct_match.group("path")
    constants = {
        match.group("name"): match.group("path")
        for match in re.finditer(r'const\s+(?P<name>[A-Z0-9_]+)\s*[:=][^"\n]*"(?P<path>res://[^"]+\.tscn)"', script_text)
    }
    named_match = re.search(r"change_scene_to_file\(\s*(?P<name>[A-Z0-9_]+)\s*\)", script_text)
    if named_match:
        return str(constants.get(named_match.group("name"), ""))
    return ""


def _detect_runtime_anchor_scene_path(project_root: Path, target_scene_path: str, script_path: str) -> str:
    candidate_paths: list[str] = []
    for path in _list_scene_paths_from_file(project_root, target_scene_path):
        if path not in candidate_paths:
            candidate_paths.append(path)
    if script_path:
        for path in _list_scene_paths_from_file(project_root, script_path):
            if path not in candidate_paths:
                candidate_paths.append(path)
    preferred_keywords = ("hud", "overlay", "ui", "crosshair")
    for path in candidate_paths:
        lowered = path.lower()
        if any(keyword in lowered for keyword in preferred_keywords):
            root_name = _parse_scene_root_name(_read_text_if_file(_resolve_res_path(project_root, path)))
            if root_name:
                return path
    return ""


def _list_scene_paths_from_file(project_root: Path, raw_path: str) -> list[str]:
    file_text = _read_text_if_file(_resolve_res_path(project_root, raw_path))
    if not file_text:
        return []
    paths: list[str] = []
    for match in re.finditer(r'"(?P<path>res://[^"]+\.tscn)"', file_text):
        path = match.group("path")
        if path != raw_path and _resolve_res_path(project_root, path).is_file() and path not in paths:
            paths.append(path)
    return paths


def _parse_scene_root_name(scene_text: str) -> str:
    match = re.search(r'\[node name="([^"]+)" type="[^"]+"\]', scene_text)
    if match:
        return match.group(1)
    return ""


def _resolve_res_path(project_root: Path, raw_path: str) -> Path | None:
    normalized = raw_path.replace("\\", "/").strip()
    if not normalized:
        return None
    if normalized.startswith("res://"):
        normalized = normalized[len("res://") :]
    return (project_root / Path(normalized)).resolve()


def _read_startup_scene(project_root: Path) -> str:
    project_file = project_root / "project.godot"
    if not project_file.is_file():
        return ""
    current_section = ""
    try:
        lines = project_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip().lower()
            continue
        if current_section != "application":
            continue
        if not line.startswith("run/main_scene="):
            continue
        value = line.split("=", 1)[1].strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        return value
    return ""
