from __future__ import annotations

import json
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
    if detected_targets.get("mode") == "start_button_to_game_level":
        steps: list[dict[str, Any]] = [
            {"id": "launch_game", "action": "launchGame"},
            {
                "id": "wait_start_button",
                "action": "wait",
                "until": {"hint": "node_exists:StartButton"},
                "timeoutMs": 5000,
            },
            {
                "id": "click_start",
                "action": "click",
                "target": {"hint": "node_name:StartButton"},
            },
            {
                "id": "wait_game_level",
                "action": "wait",
                "until": {"hint": "node_exists:GameLevel"},
                "timeoutMs": 5000,
            },
            {"id": "check_game_pointer_hud", "action": "check", "hint": "node_exists:GamePointerHud"},
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
    if startup_scene_path and startup_scene_path.is_file():
        related_files.append(startup_scene)
        startup_text = startup_scene_path.read_text(encoding="utf-8", errors="ignore")
    else:
        startup_text = ""
    start_screen_path = project_root / "scenes" / "ui" / "ui_start_screen.tscn"
    game_level_path = project_root / "scenes" / "game_level.tscn"
    hud_path = project_root / "scenes" / "ui" / "game_pointer_hud.tscn"
    start_screen_has_button = start_screen_path.is_file() and "StartButton" in start_screen_path.read_text(
        encoding="utf-8", errors="ignore"
    )
    startup_mentions_start = "ui_start_screen.tscn" in startup_text or "main_menu_flow.gd" in startup_text
    game_level_has_root = game_level_path.is_file() and 'node name="GameLevel"' in game_level_path.read_text(
        encoding="utf-8", errors="ignore"
    )
    hud_exists = hud_path.is_file()
    if start_screen_has_button and startup_mentions_start and game_level_has_root and hud_exists:
        related_files.extend(
            [
                "res://scenes/ui/ui_start_screen.tscn",
                "res://scenes/game_level.tscn",
                "res://scenes/ui/game_pointer_hud.tscn",
            ]
        )
        return {"mode": "start_button_to_game_level", "related_files": related_files}
    return {"mode": "generic_runtime_probe", "related_files": related_files}


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
