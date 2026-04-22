from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .test_project_bug_case import create_bug_case
from .test_project_bug_round import (
    create_round_id,
    parse_files_to_record,
    project_relative_to_absolute_path,
    project_relative_to_res_path,
    record_bug_round_baseline,
    update_bug_injection_plan,
)


def _timestamp(*, now_fn: Callable[[], datetime] = datetime.now) -> str:
    return now_fn().isoformat(timespec="seconds")


def _snake_case(name: str) -> str:
    cleaned = str(name or "").strip()
    if not cleaned:
        return ""
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", cleaned).replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.lower().strip("_")


def _handler_name(args: Any) -> str:
    explicit = str(getattr(args, "handler_name", "") or "").strip()
    if explicit:
        return explicit
    node_name = str(getattr(args, "location_node", "") or "").strip()
    snake = _snake_case(node_name)
    return f"_on_{snake}_pressed" if snake else ""


def _bug_id(args: Any, bug_kind: str, *, now_fn: Callable[[], datetime] = datetime.now) -> str:
    explicit = str(getattr(args, "bug_id", "") or "").strip()
    if explicit:
        return explicit
    return f"{bug_kind}-{now_fn().strftime('%H%M%S')}"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _newline_for(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _inject_return_into_handler(script_text: str, handler_name: str, marker: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf"(?m)^(?P<indent>\s*)func\s+{re.escape(handler_name)}\s*\([^)]*\)\s*(?:->\s*[\w\.]+)?\s*:\s*\r?\n"
    )
    match = pattern.search(script_text)
    if match is None:
        return script_text, False
    if marker in script_text:
        return script_text, False
    indent = match.group("indent")
    newline = _newline_for(script_text)
    injected_line = f"{indent}\treturn  # {marker}{newline}"
    updated = script_text[: match.end()] + injected_line + script_text[match.end() :]
    return updated, True


def _disable_scene_transition(script_text: str, marker: str) -> tuple[str, bool]:
    if marker in script_text:
        return script_text, False
    newline = _newline_for(script_text)
    patterns = [
        re.compile(r"(?m)^(?P<indent>\s*)(?P<prefix>var\s+\w+\s*:=\s*)[^\n]*change_scene_to_file\([^\n]+\)\s*$"),
        re.compile(r"(?m)^(?P<indent>\s*)change_scene_to_file\([^\n]+\)\s*$"),
    ]
    for pattern in patterns:
        match = pattern.search(script_text)
        if match is None:
            continue
        indent = match.groupdict().get("indent", "")
        prefix = match.groupdict().get("prefix", "")
        replacement = (
            f"{indent}{prefix}OK  # {marker}{newline}"
            if prefix
            else f"{indent}return  # {marker}{newline}"
        )
        updated = script_text[: match.start()] + replacement + script_text[match.end() :]
        return updated, True
    return script_text, False


def _set_node_property(scene_text: str, node_name: str, property_name: str, property_value: str) -> tuple[str, bool]:
    node_pattern = re.compile(rf'(?m)^\[node name="{re.escape(node_name)}"[^\n]*\]\s*$')
    node_match = node_pattern.search(scene_text)
    if node_match is None:
        return scene_text, False
    block_start = node_match.end()
    next_section = re.search(r"(?m)^\[", scene_text[block_start:])
    block_end = block_start + next_section.start() if next_section else len(scene_text)
    block_text = scene_text[block_start:block_end]
    property_pattern = re.compile(rf"(?m)^(?P<indent>\s*){re.escape(property_name)}\s*=.*$")
    property_match = property_pattern.search(block_text)
    desired_line = f"{property_name} = {property_value}"
    if property_match is not None:
        existing_line = property_match.group(0).strip()
        if existing_line == desired_line:
            return scene_text, False
        replacement = f"{property_match.group('indent')}{desired_line}"
        updated_block = block_text[: property_match.start()] + replacement + block_text[property_match.end() :]
        return scene_text[:block_start] + updated_block + scene_text[block_end:], True
    newline = _newline_for(scene_text)
    updated_block = f"{newline}{desired_line}" + block_text
    return scene_text[:block_start] + updated_block + scene_text[block_end:], True


def _disable_pointer_hud_spawn(script_text: str, marker: str) -> tuple[str, bool]:
    if marker in script_text:
        return script_text, False
    pattern = re.compile(r"(?m)^(?P<indent>\s*)add_child\(POINTER_HUD\.instantiate\(\)\)\s*$")
    match = pattern.search(script_text)
    if match is None:
        return script_text, False
    replacement = f"{match.group('indent')}pass  # {marker}"
    updated = script_text[: match.start()] + replacement + script_text[match.end() :]
    return updated, True


def _seed_button_callback_broken(script_path: Path, handler_name: str) -> dict[str, Any]:
    if not handler_name:
        raise ValueError("button_signal_or_callback_broken requires --location-node or --handler-name")
    script_text = _read_text(script_path)
    marker = "gpf_seeded_bug:button_callback_disabled"
    updated, changed = _inject_return_into_handler(script_text, handler_name, marker)
    if not changed:
        raise ValueError(f"could not inject a button callback bug into handler {handler_name}")
    _write_text(script_path, updated)
    return {
        "mutation_kind": "button_signal_or_callback_broken",
        "handler_name": handler_name,
        "marker": marker,
        "message": f"inserted an early return into {handler_name}",
    }


def _seed_scene_transition_not_triggered(script_path: Path) -> dict[str, Any]:
    script_text = _read_text(script_path)
    marker = "gpf_seeded_bug:scene_transition_disabled"
    updated, changed = _disable_scene_transition(script_text, marker)
    if not changed:
        raise ValueError("could not disable a scene transition call in the target script")
    _write_text(script_path, updated)
    return {
        "mutation_kind": "scene_transition_not_triggered",
        "marker": marker,
        "message": "disabled one change_scene_to_file call",
    }


def _rename_scene_node(scene_text: str, node_name: str, replacement_name: str) -> tuple[str, bool]:
    pattern = re.compile(rf'(?m)^(\[node name="){re.escape(node_name)}(".*\]\s*)$')
    match = pattern.search(scene_text)
    if match is None:
        return scene_text, False
    updated = scene_text[: match.start()] + f'{match.group(1)}{replacement_name}{match.group(2)}' + scene_text[match.end() :]
    return updated, True


def _seed_button_node_renamed_in_scene(scene_path: Path, node_name: str) -> dict[str, Any]:
    if not node_name:
        raise ValueError("button_node_renamed_in_scene requires --location-node")
    scene_text = _read_text(scene_path)
    renamed_to = f"{node_name}SeededBug"
    updated, changed = _rename_scene_node(scene_text, node_name, renamed_to)
    if not changed:
        raise ValueError(f"could not rename scene node {node_name}")
    _write_text(scene_path, updated)
    return {
        "mutation_kind": "button_node_renamed_in_scene",
        "node_name": node_name,
        "renamed_to": renamed_to,
        "message": f"renamed scene node {node_name} to {renamed_to}",
    }


def _seed_pointer_hud_not_spawned(script_path: Path) -> dict[str, Any]:
    script_text = _read_text(script_path)
    marker = "gpf_seeded_bug:pointer_hud_not_spawned"
    updated, changed = _disable_pointer_hud_spawn(script_text, marker)
    if not changed:
        raise ValueError("could not disable the pointer HUD spawn line in the target script")
    _write_text(script_path, updated)
    return {
        "mutation_kind": "pointer_hud_not_spawned",
        "marker": marker,
        "message": "disabled the pointer HUD instantiate path",
    }


def _bug_report_payload_from_args(args: Any, location_script: str) -> dict[str, Any]:
    return {
        "bug_report": str(getattr(args, "bug_report", "") or "").strip(),
        "bug_summary": str(getattr(args, "bug_summary", "") or "").strip(),
        "expected_behavior": str(getattr(args, "expected_behavior", "") or "").strip(),
        "steps_to_trigger": str(getattr(args, "steps_to_trigger", "") or "").strip(),
        "location_scene": str(getattr(args, "location_scene", "") or "").strip(),
        "location_node": str(getattr(args, "location_node", "") or "").strip(),
        "location_script": str(getattr(args, "location_script", "") or "").strip() or location_script,
        "frequency_hint": str(getattr(args, "frequency_hint", "") or "").strip(),
        "severity_hint": str(getattr(args, "severity_hint", "") or "").strip(),
    }


def _normalize_recorded_files(project_root: Path, args: Any, *, extra_files: list[str]) -> list[str]:
    return [
        item
        for item in parse_files_to_record(project_root, args, extra_files=extra_files)
        if project_relative_to_absolute_path(project_root, item).is_file()
    ]


def _affected_file_entry(project_root: Path, project_relative_path: str) -> dict[str, Any]:
    absolute_path = project_relative_to_absolute_path(project_root, project_relative_path)
    return {
        "project_relative_path": project_relative_path,
        "res_path": project_relative_to_res_path(project_relative_path),
        "absolute_path": str(absolute_path),
    }


def _bug_expected_target(bug_kind: str) -> dict[str, Any]:
    if bug_kind == "button_signal_or_callback_broken":
        return {
            "expected_repro_status": "bug_reproduced",
            "verification_focus": "button callback path should stop producing the expected runtime change",
        }
    if bug_kind == "scene_transition_not_triggered":
        return {
            "expected_repro_status": "bug_reproduced",
            "verification_focus": "scene transition should remain blocked after the trigger",
        }
    if bug_kind == "button_node_renamed_in_scene":
        return {
            "expected_repro_status": "trigger_failed",
            "verification_focus": "the target button node should no longer be reachable by its expected name",
        }
    return {
        "expected_repro_status": "bug_reproduced",
        "verification_focus": "the gameplay HUD should remain absent after the scene loads",
    }


def _validate_seed_args(args: Any) -> str:
    bug_kind = str(getattr(args, "bug_kind", "") or "").strip()
    supported_bug_kinds = {
        "button_signal_or_callback_broken",
        "scene_transition_not_triggered",
        "button_node_renamed_in_scene",
        "pointer_hud_not_spawned",
    }
    if bug_kind not in supported_bug_kinds:
        raise ValueError(
            "--bug-kind must be one of: button_signal_or_callback_broken, scene_transition_not_triggered, "
            "button_node_renamed_in_scene, pointer_hud_not_spawned"
        )
    if not str(getattr(args, "bug_report", "") or "").strip():
        raise ValueError("--bug-report is required for seed_test_project_bug")
    if not str(getattr(args, "expected_behavior", "") or "").strip():
        raise ValueError("--expected-behavior is required for seed_test_project_bug")
    if bug_kind in {"button_signal_or_callback_broken", "scene_transition_not_triggered", "pointer_hud_not_spawned"} and not str(
        getattr(args, "location_script", "") or ""
    ).strip():
        raise ValueError("--location-script is required for seed_test_project_bug")
    if bug_kind == "button_node_renamed_in_scene" and not str(getattr(args, "location_scene", "") or "").strip():
        raise ValueError("--location-scene is required for button_node_renamed_in_scene")
    return bug_kind


def seed_test_project_bug(
    project_root: Path,
    args: Any,
    *,
    create_round_id_fn: Callable[[], str] = create_round_id,
    now_fn: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    bug_kind = _validate_seed_args(args)
    round_id = str(getattr(args, "round_id", "") or "").strip() or create_round_id_fn()
    bug_id = _bug_id(args, bug_kind, now_fn=now_fn)
    project_relative_script = str(getattr(args, "location_script", "") or "").strip()
    project_relative_scene = str(getattr(args, "location_scene", "") or "").strip()
    script_res_path = (
        project_relative_script
        if project_relative_script.startswith("res://")
        else project_relative_to_res_path(project_relative_script)
    )

    script_path: Path | None = None
    if project_relative_script:
        script_path = project_relative_to_absolute_path(project_root, project_relative_script)
        if not script_path.is_file():
            raise ValueError(f"target script does not exist: {script_res_path}")

    mutated_files: list[str] = []
    if project_relative_script:
        mutated_files.append(project_relative_script)
    if bug_kind == "button_node_renamed_in_scene":
        mutated_files.append(project_relative_scene)

    files_to_record = _normalize_recorded_files(project_root, args, extra_files=mutated_files)
    if not files_to_record:
        files_to_record = mutated_files[:]

    planned_bug = {
        "bug_id": bug_id,
        "bug_kind": bug_kind,
        "status": "planned",
        "target_script": script_res_path,
        "target_scene": project_relative_scene,
        "location_node": str(getattr(args, "location_node", "") or "").strip(),
        "planned_at": _timestamp(now_fn=now_fn),
    }
    baseline_payload = record_bug_round_baseline(
        project_root,
        round_id,
        files_to_record,
        bug_context=_bug_report_payload_from_args(args, script_res_path) | {"bug_kind": bug_kind},
        planned_bugs=[planned_bug],
        now_fn=now_fn,
    )

    if bug_kind == "button_signal_or_callback_broken":
        assert script_path is not None
        mutation = _seed_button_callback_broken(script_path, _handler_name(args))
    elif bug_kind == "scene_transition_not_triggered":
        assert script_path is not None
        mutation = _seed_scene_transition_not_triggered(script_path)
    elif bug_kind == "button_node_renamed_in_scene":
        scene_path = project_relative_to_absolute_path(project_root, project_relative_scene)
        if not scene_path.is_file():
            raise ValueError(f"target scene does not exist: {project_relative_to_res_path(project_relative_scene)}")
        mutation = _seed_button_node_renamed_in_scene(scene_path, str(getattr(args, "location_node", "") or "").strip())
    else:
        assert script_path is not None
        mutation = _seed_pointer_hud_not_spawned(script_path)

    expected_target = _bug_expected_target(bug_kind)
    affected_files = [_affected_file_entry(project_root, item) for item in files_to_record]
    bug_case = create_bug_case(
        project_root,
        round_id,
        bug_id,
        injected_bug_kind=bug_kind,
        affected_files=affected_files,
        bug_report_payload=_bug_report_payload_from_args(args, script_res_path),
        expected_verification_target=expected_target,
        now_fn=now_fn,
    )
    injection_record = {
        "bug_id": bug_id,
        "bug_kind": bug_kind,
        "status": "applied",
        "bug_source": "injected",
        "target_script": script_res_path,
        "target_scene": project_relative_scene,
        "bug_case_file": bug_case["bug_case_file"],
        "affected_files": affected_files,
        "bug_report_payload": bug_case["bug_report_payload"],
        "expected_verification_target": expected_target,
        "mutation": mutation,
        "applied_at": _timestamp(now_fn=now_fn),
    }
    update_bug_injection_plan(project_root, round_id, injection_record, now_fn=now_fn)
    return {
        "schema": "pointer_gpf.v2.test_project_bug_seed.v1",
        "project_root": str(project_root.resolve()),
        "round_id": round_id,
        "bug_id": bug_id,
        "bug_source": "injected",
        "injected_bug_kind": bug_kind,
        "status": "bug_seeded",
        "baseline_manifest_file": baseline_payload["baseline_manifest_file"],
        "bug_injection_plan_file": baseline_payload["bug_injection_plan_file"],
        "restore_plan_file": baseline_payload["restore_plan_file"],
        "bug_case_file": bug_case["bug_case_file"],
        "affected_files": affected_files,
        "mutation": mutation,
    }
