from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .contracts import (
    ERR_BASICFLOW_GENERATION_ANSWERS_REQUIRED,
    ERR_BASICFLOW_GENERATION_SESSION_INCOMPLETE,
    ERR_BASICFLOW_GENERATION_SESSION_INVALID,
    ERR_BASICFLOW_GENERATION_SESSION_NOT_FOUND,
    ERR_BASICFLOW_MISSING,
    ERR_BASICFLOW_STALE,
    ERR_ENGINE_RUNTIME_STALLED,
    ERR_FLOW_ALREADY_RUNNING,
    ERR_MULTIPLE_EDITOR_PROCESSES_DETECTED,
    ERR_PREFLIGHT_FAILED,
    ERR_STEP_FAILED,
    ERR_TEARDOWN_VERIFICATION_FAILED,
    ERR_TIMEOUT,
    ERR_UNKNOWN_TOOL,
    build_error_payload,
    build_ok_payload,
)
from .basicflow_assets import basicflow_paths, load_basicflow_assets, mark_basicflow_run_success
from .basicflow_generation import (
    generate_basicflow_from_answers,
    generate_basicflow_from_answers_file,
    get_basicflow_generation_questions,
)
from .basicflow_generation_session import (
    BasicFlowGenerationSessionError,
    answer_basicflow_generation_session,
    complete_basicflow_generation_session,
    start_basicflow_generation_session,
)
from .basicflow_staleness import analyze_basicflow_staleness, detect_basicflow_staleness
from .flow_runner import (
    FlowExecutionEngineStalled,
    FlowExecutionStepFailed,
    FlowExecutionTimeout,
    load_flow,
    run_basic_flow,
)
from .godot_locator import configure_godot_executable, load_godot_executable
from .plugin_sync import sync_plugin
from .preflight import run_preflight


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pointer GPF V2 scaffold")
    parser.add_argument("--tool", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--flow-file")
    parser.add_argument("--godot-executable")
    parser.add_argument("--plugin-source")
    parser.add_argument("--answers-file")
    parser.add_argument("--allow-stale-basicflow", action="store_true")
    parser.add_argument("--main-scene-is-entry")
    parser.add_argument("--tested-features")
    parser.add_argument("--include-screenshot-evidence")
    parser.add_argument("--entry-scene-path")
    parser.add_argument("--session-id")
    parser.add_argument("--question-id")
    parser.add_argument("--answer")
    return parser.parse_args()


def _ok(result: dict[str, Any]) -> None:
    print(json.dumps(build_ok_payload(result), ensure_ascii=False))


def _err(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    print(json.dumps(build_error_payload(code, message, details), ensure_ascii=False))


def _bridge_dir(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp").resolve()


def _runtime_gate_path(project_root: Path) -> Path:
    return _bridge_dir(project_root) / "runtime_gate.json"


def _flow_lock_path(project_root: Path) -> Path:
    return _bridge_dir(project_root) / "flow_run.lock"


def _read_runtime_gate(project_root: Path) -> dict[str, Any]:
    gate_path = _runtime_gate_path(project_root)
    if not gate_path.is_file():
        return {}
    try:
        data = json.loads(gate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _list_project_processes(project_root: Path) -> list[dict[str, Any]]:
    target = str(project_root.resolve())
    probe = (
        "$target = '{target}'; "
        "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object {{ $_.Name -like 'Godot*.exe' -and $_.CommandLine -match [regex]::Escape($target) }} | "
        "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    ).format(target=target)
    result = subprocess.run(
        ["powershell", "-Command", probe],
        capture_output=True,
        text=True,
        timeout=10,
    )
    raw = result.stdout.strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            out.append(item)
    return out


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    probe = f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Id"
    result = subprocess.run(
        ["powershell", "-Command", probe],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return bool(result.stdout.strip())


def _is_editor_process_running(project_root: Path) -> bool:
    return bool(_list_project_processes(project_root))


def _request_auto_enter_play(project_root: Path) -> Path:
    target = _bridge_dir(project_root) / "auto_enter_play_mode.flag"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"schema": "pointer_gpf.v2.auto_enter.v1"}), encoding="utf-8")
    return target


def _launch_editor_if_needed(project_root: Path, timeout_ms: int = 12000) -> dict[str, Any]:
    gate_path = _runtime_gate_path(project_root)
    if _is_editor_process_running(project_root):
        if gate_path.is_file():
            try:
                data = json.loads(gate_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            if isinstance(data, dict):
                return {"status": "already_available", "runtime_gate": data}
        return {"status": "editor_running", "runtime_gate": {}}
    if gate_path.is_file():
        try:
            data = json.loads(gate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            gate_path.unlink(missing_ok=True)
    executable = load_godot_executable(project_root)
    gate_path.unlink(missing_ok=True)
    subprocess.Popen([executable, "-e", "--path", str(project_root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + max(1, timeout_ms) / 1000.0
    while time.monotonic() < deadline:
        if gate_path.is_file():
            try:
                data = json.loads(gate_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(0.05)
                continue
            if isinstance(data, dict):
                return {"status": "launched_editor", "runtime_gate": data}
        time.sleep(0.05)
    raise TimeoutError(f"editor bridge was not ready within {timeout_ms} ms")


def _ensure_play_mode(project_root: Path, timeout_ms: int = 15000) -> dict[str, Any]:
    launch_meta = _launch_editor_if_needed(project_root)
    gate_path = _runtime_gate_path(project_root)
    if gate_path.is_file() and _is_editor_process_running(project_root):
        data = _read_runtime_gate(project_root)
        if isinstance(data, dict) and bool(data.get("runtime_gate_passed", False)):
            return {"status": "already_running", "runtime_gate": data, "editor_bridge": launch_meta}
    _request_auto_enter_play(project_root)
    deadline = time.monotonic() + max(1, timeout_ms) / 1000.0
    while time.monotonic() < deadline:
        if gate_path.is_file():
            data = _read_runtime_gate(project_root)
            if isinstance(data, dict) and bool(data.get("runtime_gate_passed", False)):
                return {"status": "entered_play_mode", "runtime_gate": data, "editor_bridge": launch_meta}
        time.sleep(0.05)
    raise TimeoutError(f"play mode was not entered within {timeout_ms} ms")


def _flow_requests_close(flow_payload: dict[str, Any]) -> bool:
    steps = flow_payload.get("steps", [])
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("action", "")).strip().lower() == "closeproject":
            return True
    return False


def _verify_teardown(project_root: Path, timeout_ms: int = 10000) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000.0
    last_gate = _read_runtime_gate(project_root)
    last_processes = _list_project_processes(project_root)
    while time.monotonic() < deadline:
        last_gate = _read_runtime_gate(project_root)
        last_processes = _list_project_processes(project_root)
        play_stopped = not bool(last_gate.get("runtime_gate_passed", False))
        process_count_ok = len(last_processes) <= 1
        if play_stopped and process_count_ok:
            return {
                "status": "verified",
                "runtime_gate": last_gate,
                "project_process_count": len(last_processes),
                "project_processes": last_processes,
            }
        time.sleep(0.1)
    return {
        "status": "failed",
        "runtime_gate": last_gate,
        "project_process_count": len(last_processes),
        "project_processes": last_processes,
    }


def _read_flow_lock(project_root: Path) -> dict[str, Any]:
    lock_path = _flow_lock_path(project_root)
    if not lock_path.is_file():
        return {}
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _detect_multiple_project_processes(project_root: Path) -> dict[str, Any] | None:
    processes = _list_project_processes(project_root)
    if len(processes) <= 1:
        return None
    return {
        "status": "multiple_editors_detected",
        "project_process_count": len(processes),
        "project_processes": processes,
        "message": "close extra Godot editor instances for this project before running a flow",
    }


def _release_flow_lock(project_root: Path, token: str) -> None:
    lock_path = _flow_lock_path(project_root)
    payload = _read_flow_lock(project_root)
    if payload.get("token") != token:
        return
    lock_path.unlink(missing_ok=True)


def _acquire_flow_lock(project_root: Path) -> dict[str, Any]:
    lock_path = _flow_lock_path(project_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_flow_lock(project_root)
    pid = os.getpid()
    current_token = uuid.uuid4().hex
    recovered_stale_lock = False
    stale_lock: dict[str, Any] | None = None
    if existing:
        existing_pid = int(existing.get("pid", -1))
        if _is_pid_running(existing_pid):
            raise RuntimeError(json.dumps(existing, ensure_ascii=False))
        if existing_pid > 0:
            recovered_stale_lock = True
            stale_lock = existing
        lock_path.unlink(missing_ok=True)
    payload = {
        "schema": "pointer_gpf.v2.flow_lock.v1",
        "pid": pid,
        "token": current_token,
        "project_root": str(project_root.resolve()),
        "recovered_stale_lock": recovered_stale_lock,
    }
    if stale_lock is not None:
        payload["stale_lock"] = stale_lock
    lock_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def _run_basic_flow_tool(
    project_root: Path,
    flow_file: Path,
    *,
    basicflow_context: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any], bool]:
    flow_payload = load_flow(flow_file)
    flow_lock: dict[str, Any] | None = None
    result = run_preflight(project_root)
    if not result.ok:
        return 2, build_error_payload(ERR_PREFLIGHT_FAILED, "project preflight failed", result.to_dict()), False
    multi_editor = _detect_multiple_project_processes(project_root)
    if multi_editor is not None:
        return (
            2,
            build_error_payload(
                ERR_MULTIPLE_EDITOR_PROCESSES_DETECTED,
                "multiple Godot editor processes are open for this project",
                {"project_processes": multi_editor},
            ),
            False,
        )
    try:
        flow_lock = _acquire_flow_lock(project_root)
    except RuntimeError as exc:
        return (
            2,
            build_error_payload(
                ERR_FLOW_ALREADY_RUNNING,
                "another flow is already running for this project",
                {"flow_lock": json.loads(str(exc)) if str(exc).strip().startswith("{") else {"raw": str(exc)}},
            ),
            False,
        )

    try:
        play_meta = _ensure_play_mode(project_root)
        try:
            run_result = run_basic_flow(project_root, flow_file)
        except FlowExecutionStepFailed as exc:
            return (
                2,
                build_error_payload(
                    ERR_STEP_FAILED,
                    str(exc),
                    {"run_id": exc.run_id, "step_index": exc.step_index, "step_id": exc.step_id, "play_mode": play_meta},
                ),
                False,
            )
        except FlowExecutionTimeout as exc:
            return (
                2,
                build_error_payload(
                    ERR_TIMEOUT,
                    str(exc),
                    {"run_id": exc.run_id, "step_index": exc.step_index, "step_id": exc.step_id, "play_mode": play_meta},
                ),
                False,
            )
        except FlowExecutionEngineStalled as exc:
            return (
                2,
                build_error_payload(
                    ERR_ENGINE_RUNTIME_STALLED,
                    str(exc),
                    {
                        "run_id": exc.run_id,
                        "step_index": exc.step_index,
                        "step_id": exc.step_id,
                        "runtime_diagnostics": exc.diagnostics,
                        "play_mode": play_meta,
                    },
                ),
                False,
            )
        teardown_meta: dict[str, Any] | None = None
        if _flow_requests_close(flow_payload):
            teardown_meta = _verify_teardown(project_root)
            if teardown_meta["status"] != "verified":
                return (
                    2,
                    build_error_payload(
                        ERR_TEARDOWN_VERIFICATION_FAILED,
                        "play mode did not fully stop after closeProject",
                        {"play_mode": play_meta, "execution": run_result, "project_close": teardown_meta},
                    ),
                    False,
                )
        payload = {"play_mode": play_meta, "execution": run_result}
        if teardown_meta is not None:
            payload["project_close"] = teardown_meta
        if flow_lock is not None:
            payload["flow_guard"] = {
                "recovered_stale_lock": bool(flow_lock.get("recovered_stale_lock", False)),
                "stale_lock": flow_lock.get("stale_lock", {}),
            }
        if basicflow_context is not None:
            project_basicflow = basicflow_paths(project_root).flow_file
            if flow_file.resolve() == project_basicflow.resolve():
                payload["basicflow"] = {
                    "status": basicflow_context.get("status", "fresh"),
                    "flow_summary": basicflow_context.get("flow_summary", ""),
                    "used_project_basicflow": True,
                }
                if basicflow_context.get("status") == "stale":
                    payload["basicflow"]["warning"] = "ran stale basicflow because allow-stale-basicflow was set"
                    payload["basicflow"]["staleness"] = basicflow_context
                updated_meta = mark_basicflow_run_success(project_root)
                payload["basicflow"]["last_successful_run_at"] = updated_meta.get("last_successful_run_at")
        return 0, build_ok_payload(payload), True
    finally:
        if flow_lock is not None:
            _release_flow_lock(project_root, str(flow_lock.get("token", "")))


def _basicflow_missing_payload(project_root: Path) -> dict[str, Any]:
    return build_error_payload(
        ERR_BASICFLOW_MISSING,
        "basicflow assets do not exist yet for this project",
        {
            "project_root": str(project_root.resolve()),
            "next_step": "inspect the project and ask the 3 basicflow generation questions before creating assets",
            "generation_questions": [
                "当前游戏工程的主场景是否是游戏主流程的入口？",
                "你认为应该被测试的游戏功能都有哪些？",
                "测试是否需要保留截图证据？",
            ],
        },
    )


def _basicflow_stale_payload(project_root: Path, stale_result: dict[str, Any]) -> dict[str, Any]:
    return build_error_payload(
        ERR_BASICFLOW_STALE,
        "basicflow may be stale for the current project state",
        {
            "project_root": str(project_root.resolve()),
            "flow_summary": stale_result.get("flow_summary", ""),
            "staleness": stale_result,
            "choices": [
                "analyze what the old basicflow covered and where it no longer matches the project",
                "regenerate basicflow",
                "describe project changes or extra requirements",
                "run the old basicflow anyway",
            ],
        },
    )


def _resolve_requested_flow_file(
    project_root: Path,
    flow_file_arg: str | None,
    *,
    allow_stale_basicflow: bool,
) -> tuple[Path | None, dict[str, Any] | None, dict[str, Any] | None]:
    if flow_file_arg:
        return Path(flow_file_arg), None, None
    stale_result = detect_basicflow_staleness(project_root)
    if stale_result["status"] == "missing":
        return None, _basicflow_missing_payload(project_root), None
    if stale_result["status"] == "stale":
        if not allow_stale_basicflow:
            return None, _basicflow_stale_payload(project_root, stale_result), None
        assets = load_basicflow_assets(project_root)
        return Path(assets["paths"]["flow_file"]), None, stale_result
    assets = load_basicflow_assets(project_root)
    return Path(assets["paths"]["flow_file"]), None, stale_result


def _parse_bool_arg(raw: str | None) -> bool | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y"}:
        return True
    if value in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"invalid boolean value: {raw!r}")


def _collect_inline_generation_answers(args: argparse.Namespace) -> dict[str, Any] | None:
    has_any_inline = any(
        getattr(args, name, None) not in {None, ""}
        for name in ("main_scene_is_entry", "tested_features", "include_screenshot_evidence", "entry_scene_path")
    )
    if not has_any_inline:
        return None
    main_scene_is_entry = _parse_bool_arg(getattr(args, "main_scene_is_entry", None))
    include_screenshot_evidence = _parse_bool_arg(getattr(args, "include_screenshot_evidence", None))
    if main_scene_is_entry is None or include_screenshot_evidence is None:
        raise ValueError("main_scene_is_entry and include_screenshot_evidence are required when using inline generation answers")
    tested_features_raw = getattr(args, "tested_features", None)
    if not tested_features_raw:
        raise ValueError("tested_features is required when using inline generation answers")
    return {
        "main_scene_is_entry": main_scene_is_entry,
        "tested_features": str(tested_features_raw),
        "include_screenshot_evidence": include_screenshot_evidence,
        "entry_scene_path": getattr(args, "entry_scene_path", None),
    }


def main() -> int:
    args = _parse_args()
    project_root = Path(args.project_root)
    try:
        if args.tool == "configure_godot_executable":
            if not args.godot_executable:
                raise ValueError("--godot-executable is required")
            target = configure_godot_executable(project_root, args.godot_executable)
            _ok({"status": "configured", "config_file": str(target)})
            return 0

        if args.tool == "sync_godot_plugin":
            src = Path(args.plugin_source) if args.plugin_source else Path(__file__).resolve().parents[1] / "godot_plugin" / "addons" / "pointer_gpf"
            dst = sync_plugin(src, project_root)
            _ok({"status": "synced", "destination": str(dst)})
            return 0

        if args.tool == "preflight_project":
            result = run_preflight(project_root)
            _ok(result.to_dict())
            return 0 if result.ok else 2

        if args.tool == "run_basic_flow":
            requested_flow_file, early_response, basicflow_context = _resolve_requested_flow_file(
                project_root,
                args.flow_file,
                allow_stale_basicflow=bool(getattr(args, "allow_stale_basicflow", False)),
            )
            if early_response is not None:
                print(json.dumps(early_response, ensure_ascii=False))
                return 2
            if requested_flow_file is None:
                raise ValueError("run_basic_flow could not resolve a flow file")
            exit_code, response, is_ok = _run_basic_flow_tool(
                project_root,
                requested_flow_file,
                basicflow_context=basicflow_context,
            )
            print(json.dumps(response, ensure_ascii=False))
            return exit_code

        if args.tool == "generate_basic_flow":
            inline_answers = _collect_inline_generation_answers(args)
            if args.answers_file:
                result = generate_basicflow_from_answers_file(project_root, Path(args.answers_file))
            elif inline_answers is not None:
                result = generate_basicflow_from_answers(project_root, inline_answers)
            else:
                _err(
                    ERR_BASICFLOW_GENERATION_ANSWERS_REQUIRED,
                    "generate_basic_flow requires either --answers-file or inline answers for the 3 generation questions",
                    {
                        "required_questions": [
                            "当前游戏工程的主场景是否是游戏主流程的入口？",
                            "你认为应该被测试的游戏功能都有哪些？",
                            "测试是否需要保留截图证据？",
                        ],
                        "inline_args": [
                            "--main-scene-is-entry",
                            "--tested-features",
                            "--include-screenshot-evidence",
                            "--entry-scene-path (required only when main scene is not the real entry)",
                        ],
                    },
                )
                return 2
            _ok(
                {
                    "status": "generated",
                    "flow_file": result["paths"]["flow_file"],
                    "meta_file": result["paths"]["meta_file"],
                    "generation_summary": result["meta"]["generation_summary"],
                    "step_count": len(result["flow"]["steps"]),
                }
            )
            return 0

        if args.tool == "get_basic_flow_generation_questions":
            _ok(get_basicflow_generation_questions(project_root))
            return 0

        if args.tool == "start_basic_flow_generation_session":
            _ok(start_basicflow_generation_session(project_root))
            return 0

        if args.tool == "answer_basic_flow_generation_session":
            if not args.session_id or not args.question_id or args.answer is None:
                raise ValueError("--session-id, --question-id, and --answer are required")
            _ok(
                answer_basicflow_generation_session(
                    project_root,
                    session_id=str(args.session_id),
                    question_id=str(args.question_id),
                    answer=str(args.answer),
                )
            )
            return 0

        if args.tool == "complete_basic_flow_generation_session":
            if not args.session_id:
                raise ValueError("--session-id is required")
            _ok(complete_basicflow_generation_session(project_root, session_id=str(args.session_id)))
            return 0

        if args.tool == "analyze_basic_flow_staleness":
            _ok(analyze_basicflow_staleness(project_root))
            return 0

        _err(ERR_UNKNOWN_TOOL, f"unsupported tool: {args.tool}")
        return 1
    except BasicFlowGenerationSessionError as exc:
        message = str(exc)
        if "no active basicflow generation session" in message:
            _err(ERR_BASICFLOW_GENERATION_SESSION_NOT_FOUND, message)
            return 2
        if "incomplete" in message:
            _err(ERR_BASICFLOW_GENERATION_SESSION_INCOMPLETE, message)
            return 2
        _err(ERR_BASICFLOW_GENERATION_SESSION_INVALID, message)
        return 2
    except Exception as exc:
        _err(type(exc).__name__.upper(), str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
