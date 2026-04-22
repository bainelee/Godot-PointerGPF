from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .bug_fix_planning import plan_bug_fix


def _snake_case(name: str) -> str:
    cleaned = str(name or "").strip()
    if not cleaned:
        return ""
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", cleaned).replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.lower().strip("_")


def _handler_name(node_name: str) -> str:
    snake = _snake_case(node_name)
    return f"_on_{snake}_pressed" if snake else ""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _append_bind_helper(script_text: str, node_name: str, handler_name: str, newline: str) -> str:
    helper = (
        f"{newline}{newline}"
        f"func _gpf_bind_bug_trigger_signal() -> void:{newline}"
        f"\tvar trigger := find_child(\"{node_name}\", true, false) as Button{newline}"
        f"\tif trigger and not trigger.pressed.is_connected({handler_name}):{newline}"
        f"\t\ttrigger.pressed.connect({handler_name}){newline}"
    )
    return script_text.rstrip() + helper


def _append_scene_transition_helper(script_text: str, target_scene: str, newline: str) -> str:
    helper = (
        f"{newline}{newline}"
        f"func _gpf_change_to_expected_scene() -> void:{newline}"
        f"\tvar tree := get_tree(){newline}"
        f"\tif tree == null:{newline}"
        f"\t\treturn{newline}"
        f"\ttree.change_scene_to_file(\"{target_scene}\"){newline}"
    )
    return script_text.rstrip() + helper


def _restore_seeded_scene_transition(script_text: str, target_scene: str, newline: str) -> tuple[str, bool]:
    pattern = re.compile(r"(?m)^(?P<indent>\s*)(?P<prefix>var\s+\w+\s*:=\s*)OK\s+#\s+gpf_seeded_bug:scene_transition_disabled\s*$")
    match = pattern.search(script_text)
    if match is None:
        return script_text, False
    indent = match.group("indent")
    prefix = match.group("prefix")
    replacement = f'{indent}{prefix}tree.change_scene_to_file("{target_scene}"){newline}'
    updated = script_text[: match.start()] + replacement + script_text[match.end() :]
    return updated, True


def _inject_ready_call(script_text: str, newline: str) -> str:
    lines = script_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("func _ready("):
            indent = line[: len(line) - len(line.lstrip())]
            lines.insert(index + 1, f"{indent}\t_gpf_bind_bug_trigger_signal()")
            return newline.join(lines) + (newline if script_text.endswith(("\n", "\r")) else "")
    raise ValueError("target script does not define _ready(), so the current fix strategy cannot be applied")


def _apply_button_signal_fix(script_path: Path, node_name: str) -> dict[str, Any]:
    script_text = _read_text(script_path)
    handler_name = _handler_name(node_name)
    if not handler_name:
        return {
            "status": "fix_not_supported",
            "message": "location node is required for the current button-signal fix strategy",
            "applied": False,
        }
    if f"func {handler_name}(" not in script_text:
        return {
            "status": "fix_not_supported",
            "message": f"target script does not define handler {handler_name}",
            "applied": False,
        }
    if f"pressed.is_connected({handler_name})" in script_text or f"pressed.connect({handler_name})" in script_text:
        return {
            "status": "already_aligned",
            "message": f"target script already contains a pressed-signal connection for {handler_name}",
            "applied": False,
        }

    newline = "\r\n" if "\r\n" in script_text else "\n"
    updated = _inject_ready_call(script_text, newline)
    updated = _append_bind_helper(updated, node_name, handler_name, newline)
    _write_text(script_path, updated)
    return {
        "status": "fix_applied",
        "message": f"added guarded pressed-signal binding for {node_name} -> {handler_name}",
        "applied": True,
    }


def _target_scene_from_fix_plan(fix_plan: dict[str, Any]) -> str:
    assertions = fix_plan.get("repro_run", {}).get("repro_flow_plan", {}).get("assertion_set", {}).get("assertions", [])
    if not isinstance(assertions, list):
        return ""
    for item in assertions:
        if not isinstance(item, dict):
            continue
        if str(item.get("id", "")).strip() == "target_scene_reached":
            target = item.get("target", {})
            if isinstance(target, dict):
                return str(target.get("scene", "")).strip()
    return ""


def _handler_body(script_text: str, handler_name: str) -> str:
    handler_pattern = re.compile(
        rf"(?ms)^func\s+{re.escape(handler_name)}\s*\([^)]*\)\s*(?:->\s*[\w\.]+)?\s*:\s*\n(?P<body>.*?)(?=^func\s|\Z)"
    )
    match = handler_pattern.search(script_text)
    return str(match.group("body")) if match is not None else ""


def _apply_scene_transition_fix(script_path: Path, node_name: str, target_scene: str) -> dict[str, Any]:
    script_text = _read_text(script_path)
    handler_name = _handler_name(node_name)
    if not handler_name:
        return {
            "status": "fix_not_supported",
            "message": "location node is required for the current scene-transition fix strategy",
            "applied": False,
        }
    if not target_scene:
        return {
            "status": "fix_not_supported",
            "message": "target scene is required for the current scene-transition fix strategy",
            "applied": False,
        }
    if f"func {handler_name}(" not in script_text:
        return {
            "status": "fix_not_supported",
            "message": f"target script does not define handler {handler_name}",
            "applied": False,
        }
    handler_body = _handler_body(script_text, handler_name)
    newline = "\r\n" if "\r\n" in script_text else "\n"
    restored, restored_seeded = _restore_seeded_scene_transition(script_text, target_scene, newline)
    if restored_seeded:
        _write_text(script_path, restored)
        return {
            "status": "fix_applied",
            "message": f"restored the disabled scene transition to {target_scene} inside {handler_name}",
            "applied": True,
        }
    if "change_scene_to_file(" in handler_body or "_gpf_change_to_expected_scene()" in handler_body:
        return {
            "status": "already_aligned",
            "message": f"target script already contains a scene-transition call for {handler_name}",
            "applied": False,
        }

    handler_pattern = re.compile(rf"(func\s+{re.escape(handler_name)}\s*\([^)]*\)\s*->\s*void:\s*(?:\r?\n))")
    match = handler_pattern.search(script_text)
    if match is None:
        return {
            "status": "fix_not_supported",
            "message": f"could not locate handler body for {handler_name}",
            "applied": False,
        }
    insert_at = match.end()
    handler_call = f"\t_gpf_change_to_expected_scene(){newline}"
    updated = script_text[:insert_at] + handler_call + script_text[insert_at:]
    updated = _append_scene_transition_helper(updated, target_scene, newline)
    _write_text(script_path, updated)
    return {
        "status": "fix_applied",
        "message": f"added guarded scene transition to {target_scene} from {handler_name}",
        "applied": True,
    }


def apply_bug_fix(
    project_root: Path,
    args: Any,
    *,
    plan_bug_fix_fn: Callable[[Path, Any], dict[str, Any]] = plan_bug_fix,
) -> dict[str, Any]:
    fix_plan = plan_bug_fix_fn(project_root, args)
    if str(fix_plan.get("status", "")).strip() != "fix_ready":
        return {
            "schema": "pointer_gpf.v2.fix_apply.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": fix_plan.get("bug_summary", ""),
            "round_id": str(fix_plan.get("round_id", "")).strip(),
            "bug_id": str(fix_plan.get("bug_id", "")).strip(),
            "bug_source": str(fix_plan.get("bug_source", "pre_existing")).strip() or "pre_existing",
            "injected_bug_kind": str(fix_plan.get("injected_bug_kind", "")).strip(),
            "bug_case_file": str(fix_plan.get("bug_case_file", "")).strip(),
            "status": "fix_not_applied",
            "reason": "code changes are blocked until plan_bug_fix returns fix_ready",
            "fix_plan": fix_plan,
            "applied_changes": [],
            "next_action": str(fix_plan.get("next_action", "refine_repro_flow_or_assertions")),
        }

    repro_analysis = fix_plan.get("repro_run", {}).get("repro_flow_plan", {}).get("assertion_set", {}).get("bug_analysis", {})
    suspected_causes = repro_analysis.get("suspected_causes", [])
    bug_intake = repro_analysis.get("bug_intake", {})
    location_hint = bug_intake.get("location_hint", {})
    node_name = str(location_hint.get("node", "")).strip()
    cause_kinds = [str(item.get("kind", "")).strip() for item in suspected_causes if isinstance(item, dict)]

    candidate_files = fix_plan.get("candidate_files", [])
    target_script = ""
    for item in candidate_files:
        if not isinstance(item, dict):
            continue
        path_text = str(item.get("path", "")).strip()
        if path_text.endswith(".gd"):
            target_script = path_text
            break
    if not target_script:
        return {
            "schema": "pointer_gpf.v2.fix_apply.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": fix_plan.get("bug_summary", ""),
            "round_id": str(fix_plan.get("round_id", "")).strip(),
            "bug_id": str(fix_plan.get("bug_id", "")).strip(),
            "bug_source": str(fix_plan.get("bug_source", "pre_existing")).strip() or "pre_existing",
            "injected_bug_kind": str(fix_plan.get("injected_bug_kind", "")).strip(),
            "bug_case_file": str(fix_plan.get("bug_case_file", "")).strip(),
            "status": "fix_not_supported",
            "reason": "no candidate GDScript file was available for the current fix strategy",
            "fix_plan": fix_plan,
            "applied_changes": [],
            "next_action": "inspect_candidate_files_and_edit_code",
        }

    script_path = (project_root / target_script.replace("res://", "").replace("/", "\\")).resolve()
    if not script_path.is_file():
        return {
            "schema": "pointer_gpf.v2.fix_apply.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": fix_plan.get("bug_summary", ""),
            "round_id": str(fix_plan.get("round_id", "")).strip(),
            "bug_id": str(fix_plan.get("bug_id", "")).strip(),
            "bug_source": str(fix_plan.get("bug_source", "pre_existing")).strip() or "pre_existing",
            "injected_bug_kind": str(fix_plan.get("injected_bug_kind", "")).strip(),
            "bug_case_file": str(fix_plan.get("bug_case_file", "")).strip(),
            "status": "fix_not_supported",
            "reason": f"candidate script does not exist on disk: {target_script}",
            "fix_plan": fix_plan,
            "applied_changes": [],
            "next_action": "inspect_candidate_files_and_edit_code",
        }

    applied: dict[str, Any]
    strategy = ""
    if "button_signal_or_callback_broken" in cause_kinds:
        applied = _apply_button_signal_fix(script_path, node_name)
        strategy = "bind_button_signal_callback"
        if str(applied.get("status", "")).strip() == "already_aligned" and "scene_transition_not_triggered" in cause_kinds:
            applied = _apply_scene_transition_fix(script_path, node_name, _target_scene_from_fix_plan(fix_plan))
            strategy = "add_scene_transition_call"
    elif "scene_transition_not_triggered" in cause_kinds:
        applied = _apply_scene_transition_fix(script_path, node_name, _target_scene_from_fix_plan(fix_plan))
        strategy = "add_scene_transition_call"
    else:
        return {
            "schema": "pointer_gpf.v2.fix_apply.v1",
            "project_root": str(project_root.resolve()),
            "bug_summary": fix_plan.get("bug_summary", ""),
            "round_id": str(fix_plan.get("round_id", "")).strip(),
            "bug_id": str(fix_plan.get("bug_id", "")).strip(),
            "bug_source": str(fix_plan.get("bug_source", "pre_existing")).strip() or "pre_existing",
            "injected_bug_kind": str(fix_plan.get("injected_bug_kind", "")).strip(),
            "bug_case_file": str(fix_plan.get("bug_case_file", "")).strip(),
            "status": "fix_not_supported",
            "reason": "the current apply_bug_fix slice only supports button_signal_or_callback_broken and scene_transition_not_triggered",
            "fix_plan": fix_plan,
            "applied_changes": [],
            "next_action": "implement_another_fix_strategy",
        }
    return {
        "schema": "pointer_gpf.v2.fix_apply.v1",
        "project_root": str(project_root.resolve()),
        "bug_summary": fix_plan.get("bug_summary", ""),
        "round_id": str(fix_plan.get("round_id", "")).strip(),
        "bug_id": str(fix_plan.get("bug_id", "")).strip(),
        "bug_source": str(fix_plan.get("bug_source", "pre_existing")).strip() or "pre_existing",
        "injected_bug_kind": str(fix_plan.get("injected_bug_kind", "")).strip(),
        "bug_case_file": str(fix_plan.get("bug_case_file", "")).strip(),
        "status": str(applied.get("status", "")),
        "reason": str(applied.get("message", "")),
        "fix_plan": fix_plan,
        "applied_changes": [
            {
                "path": target_script,
                "absolute_path": str(script_path),
                "strategy": strategy,
            }
        ]
        if bool(applied.get("applied", False))
        else [],
        "next_action": "rerun_bug_repro_flow" if bool(applied.get("applied", False)) else "inspect_candidate_files_and_edit_code",
    }
