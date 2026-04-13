from __future__ import annotations

import argparse
import json
import os
import re
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
from .windows_isolated_runtime import (
    close_isolated_runtime_session,
    launch_isolated_runtime,
    verify_isolated_runtime_stopped,
)

_SUPPORTED_EXECUTION_MODES = {"play_mode", "isolated_runtime"}
_WINDOWS_EXE_PATH_RE = re.compile(r"([A-Za-z]:\\[^\"'\r\n]+?\.exe)", re.IGNORECASE)
_BASICFLOW_REQUEST_SPECS = [
    {
        "id": "run_basic_test_flow",
        "tool": "run_basic_flow",
        "purpose": "show visible engine and game control, or do a baseline confidence check",
        "user_phrases": [
            "跑基础测试流程",
            "run the basic test flow",
            "跑基础流程",
            "执行基础测试流程",
            "运行基础流程",
            "run basicflow",
            "run the basic flow",
        ],
    },
    {
        "id": "generate_basic_test_flow",
        "tool": "generate_basic_flow",
        "purpose": "create or refresh the project-local basicflow asset",
        "user_phrases": [
            "生成基础测试流程",
            "重新生成基础流程",
            "generate basicflow",
            "重建基础流程",
            "刷新基础流程",
            "regenerate basicflow",
            "generate the basic flow",
        ],
    },
    {
        "id": "analyze_basicflow_staleness",
        "tool": "analyze_basic_flow_staleness",
        "purpose": "explain where the saved project basicflow no longer matches the project",
        "user_phrases": [
            "分析基础流程为什么过期",
            "为什么 basicflow stale",
            "analyze basicflow staleness",
            "分析 basicflow",
            "检查基础流程为什么 stale",
            "why is basicflow stale",
            "inspect basicflow drift",
        ],
    },
]
_PROJECT_READINESS_REQUEST_SPECS = [
    {
        "id": "run_project_preflight",
        "domain": "project_readiness",
        "tool": "preflight_project",
        "user_phrases": [
            "跑项目预检",
            "运行项目预检",
            "检查项目状态",
            "检查工程状态",
            "检查项目能不能跑",
            "preflight project",
            "run preflight",
        ],
        "purpose": "check executable config, plugin install, runtime tmp, and UID consistency",
        "needs_explicit_path": False,
    },
    {
        "id": "configure_godot_executable_path",
        "domain": "project_readiness",
        "tool": "configure_godot_executable",
        "user_phrases": [
            "配置 godot 路径",
            "设置 godot 路径",
            "配置 godot executable",
            "set godot executable",
            "configure godot executable",
        ],
        "purpose": "save a concrete Godot executable path for this project",
        "needs_explicit_path": True,
    },
]


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
    parser.add_argument("--execution-mode", default="play_mode")
    parser.add_argument("--session-id")
    parser.add_argument("--question-id")
    parser.add_argument("--answer")
    parser.add_argument("--user-request")
    return parser.parse_args()


def _ok(result: dict[str, Any]) -> None:
    print(json.dumps(build_ok_payload(result), ensure_ascii=False))


def _err(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    print(json.dumps(build_error_payload(code, message, details), ensure_ascii=False))


def _bridge_dir(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp").resolve()


def _runtime_gate_path(project_root: Path) -> Path:
    return _bridge_dir(project_root) / "runtime_gate.json"


def _default_plugin_source() -> Path:
    return Path(__file__).resolve().parents[1] / "godot_plugin" / "addons" / "pointer_gpf"


def _sync_project_plugin(project_root: Path) -> Path:
    return sync_plugin(_default_plugin_source(), project_root)


def _flow_lock_path(project_root: Path) -> Path:
    return _bridge_dir(project_root) / "flow_run.lock"


def _normalize_execution_mode(raw: str | None) -> str:
    mode = str(raw or "play_mode").strip().lower()
    if mode not in _SUPPORTED_EXECUTION_MODES:
        supported = ", ".join(sorted(_SUPPORTED_EXECUTION_MODES))
        raise ValueError(f"unsupported execution mode: {raw!r}; supported values: {supported}")
    return mode


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
    return bool(_list_project_editor_processes(project_root))


def _list_project_editor_processes(project_root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _list_project_processes(project_root):
        command_line = str(item.get("CommandLine", ""))
        if " -e " in f" {command_line} ":
            out.append(item)
    return out


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


def _verify_teardown(project_root: Path, timeout_ms: int = 10000, *, stable_ms: int = 500) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000.0
    last_gate = _read_runtime_gate(project_root)
    last_processes = _list_project_editor_processes(project_root)
    stopped_since: float | None = None
    stable_seconds = max(0, stable_ms) / 1000.0
    last_now = time.monotonic()
    while time.monotonic() < deadline:
        now = time.monotonic()
        last_now = now
        last_gate = _read_runtime_gate(project_root)
        last_processes = _list_project_editor_processes(project_root)
        play_stopped = not bool(last_gate.get("runtime_gate_passed", False))
        process_count_ok = len(last_processes) <= 1
        if play_stopped and process_count_ok:
            if stopped_since is None:
                stopped_since = now
            stable_stop_ms = int(max(0.0, now - stopped_since) * 1000)
        else:
            stopped_since = None
            stable_stop_ms = 0
        if play_stopped and process_count_ok and stable_stop_ms >= stable_ms:
            return {
                "status": "verified",
                "runtime_gate": last_gate,
                "project_process_count": len(last_processes),
                "project_processes": last_processes,
                "stable_stop_ms": stable_stop_ms,
                "required_stable_stop_ms": stable_ms,
            }
        time.sleep(0.1)
    return {
        "status": "failed",
        "runtime_gate": last_gate,
        "project_process_count": len(last_processes),
        "project_processes": last_processes,
        "stable_stop_ms": int(max(0.0, (last_now - stopped_since) * 1000)) if stopped_since is not None else 0,
        "required_stable_stop_ms": stable_ms,
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
    processes = _list_project_editor_processes(project_root)
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
    execution_mode: str = "play_mode",
) -> tuple[int, dict[str, Any], bool]:
    execution_mode = _normalize_execution_mode(execution_mode)
    flow_payload = load_flow(flow_file)
    flow_lock: dict[str, Any] | None = None
    isolated_session = None
    plugin_destination = _sync_project_plugin(project_root)
    result = run_preflight(project_root)
    if not result.ok:
        return 2, build_error_payload(ERR_PREFLIGHT_FAILED, "project preflight failed", result.to_dict()), False
    multi_editor = _detect_multiple_project_processes(project_root) if execution_mode == "play_mode" else None
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
        if execution_mode == "isolated_runtime":
            isolated_session = launch_isolated_runtime(project_root, load_godot_executable(project_root))
            play_meta = {
                "status": "launched_isolated_runtime",
                "execution_mode": execution_mode,
                "runtime_process": {
                    "pid": isolated_session.pid,
                    "desktop_name": isolated_session.desktop_name,
                    "host_desktop_name": isolated_session.host_desktop_name,
                },
            }
        else:
            play_meta = _ensure_play_mode(project_root)
            play_meta["execution_mode"] = execution_mode
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
            teardown_meta = (
                verify_isolated_runtime_stopped(isolated_session)
                if execution_mode == "isolated_runtime" and isolated_session is not None
                else _verify_teardown(project_root)
            )
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
        isolation_meta: dict[str, Any] = {
            "isolated": execution_mode == "isolated_runtime",
            "surface": "windows_desktop" if execution_mode == "isolated_runtime" else "editor_play_mode",
            "status": "isolated_desktop" if execution_mode == "isolated_runtime" else "shared_desktop",
        }
        if execution_mode == "isolated_runtime" and isolated_session is not None:
            isolation_meta["desktop_name"] = isolated_session.desktop_name
            isolation_meta["host_desktop_name"] = isolated_session.host_desktop_name
            isolation_meta["runtime_pid"] = isolated_session.pid
            isolation_meta["separate_desktop"] = bool(
                isolated_session.desktop_name
                and isolated_session.host_desktop_name
                and isolated_session.desktop_name != isolated_session.host_desktop_name
            )
        payload = {
            "play_mode": play_meta,
            "execution": run_result,
            "execution_mode": execution_mode,
            "isolation": isolation_meta,
            "plugin_sync": {"destination": str(plugin_destination)},
        }
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
        if isolated_session is not None:
            close_isolated_runtime_session(isolated_session)
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


def _basicflow_user_intent_payload(project_root: Path) -> dict[str, Any]:
    stale_result = detect_basicflow_staleness(project_root)
    status = str(stale_result.get("status", "")).strip().lower() or "unknown"
    project_root_str = str(project_root.resolve())
    intents: list[dict[str, Any]] = [
        {
            "id": str(spec.get("id", "")).strip(),
            "user_phrases": list(spec.get("user_phrases", [])),
            "tool": str(spec.get("tool", "")).strip(),
            "purpose": str(spec.get("purpose", "")).strip(),
        }
        for spec in _BASICFLOW_REQUEST_SPECS
    ]
    primary_recommendation: dict[str, Any]
    secondary_actions: list[dict[str, Any]]
    if status == "missing":
        intents[0]["availability"] = "blocked_missing_basicflow"
        intents[0]["next_step"] = "ask the 3 generation questions, then generate the first project basicflow"
        intents[1]["availability"] = "recommended"
        intents[1]["next_step"] = "collect generation answers and create the first project basicflow"
        intents[2]["availability"] = "not_applicable"
        intents[2]["next_step"] = "no saved basicflow exists yet"
        primary_recommendation = {
            "id": intents[1]["id"],
            "tool": intents[1]["tool"],
            "reason": "the project does not have a saved basicflow yet",
            "next_step": intents[1]["next_step"],
        }
        secondary_actions = [
            {
                "id": "get_basic_flow_generation_questions",
                "tool": "get_basic_flow_generation_questions",
                "reason": "collect the 3 generation answers before creating the first project basicflow",
            }
        ]
    elif status == "stale":
        intents[0]["availability"] = "decision_required"
        intents[0]["next_step"] = "either analyze staleness, regenerate basicflow, or run with allow-stale-basicflow"
        intents[1]["availability"] = "recommended"
        intents[1]["next_step"] = "regenerate the saved project basicflow"
        intents[2]["availability"] = "recommended"
        intents[2]["next_step"] = "inspect what changed before deciding whether to regenerate or override"
        primary_recommendation = {
            "id": intents[1]["id"],
            "tool": intents[1]["tool"],
            "reason": "the saved basicflow is stale, so regeneration is the safest default",
            "next_step": intents[1]["next_step"],
        }
        secondary_actions = [
            {
                "id": intents[2]["id"],
                "tool": intents[2]["tool"],
                "reason": "inspect the project-vs-basicflow drift before choosing regenerate or override",
            },
            {
                "id": intents[0]["id"],
                "tool": intents[0]["tool"],
                "reason": "run only if the user explicitly wants to use the stale flow anyway",
                "requires": ["allow_stale_basicflow"],
            },
        ]
    else:
        intents[0]["availability"] = "recommended"
        intents[0]["next_step"] = "run the saved project basicflow"
        intents[1]["availability"] = "available"
        intents[1]["next_step"] = "regenerate only if the project intent or startup path changed"
        intents[2]["availability"] = "available"
        intents[2]["next_step"] = "use only when you want an explanation of project-vs-basicflow drift"
        primary_recommendation = {
            "id": intents[0]["id"],
            "tool": intents[0]["tool"],
            "reason": "the saved project basicflow is ready to use",
            "next_step": intents[0]["next_step"],
        }
        secondary_actions = [
            {
                "id": intents[1]["id"],
                "tool": intents[1]["tool"],
                "reason": "refresh only if the startup path or target features changed",
            },
            {
                "id": intents[2]["id"],
                "tool": intents[2]["tool"],
                "reason": "inspect drift only when the user asks for an explanation",
            },
        ]
    return {
        "status": "intents_ready",
        "project_root": project_root_str,
        "basicflow_state": status,
        "basicflow_staleness": stale_result,
        "primary_recommendation": primary_recommendation,
        "secondary_actions": secondary_actions,
        "intents": intents,
    }


def _user_request_command_guide(project_root: Path) -> dict[str, Any]:
    basicflow_catalog = _basicflow_user_intent_payload(project_root)
    readiness_catalog = _project_readiness_request_catalog(project_root)
    command_groups: list[dict[str, Any]] = []
    for intent in basicflow_catalog["intents"]:
        command_groups.append(
            {
                "id": str(intent.get("id", "")).strip(),
                "domain": "basicflow",
                "tool": str(intent.get("tool", "")).strip(),
                "user_phrases": intent.get("user_phrases", []),
                "purpose": str(intent.get("purpose", "")).strip(),
                "notes": [
                    "project-aware routing may change the next safe action based on basicflow state",
                ],
            }
        )
    for intent in readiness_catalog["intents"]:
        command_groups.append(
            {
                "id": str(intent.get("id", "")).strip(),
                "domain": str(intent.get("domain", "")).strip(),
                "tool": str(intent.get("tool", "")).strip(),
                "user_phrases": intent.get("user_phrases", []),
                "purpose": str(intent.get("purpose", "")).strip(),
                "notes": intent.get("notes", []),
            }
        )
    return {
        "status": "command_guide_ready",
        "project_root": str(project_root.resolve()),
        "supported_domains": ["basicflow", "project_readiness"],
        "core_rule": "use one short explicit request for one concrete action",
        "command_groups": command_groups,
        "unsupported_style_examples": [
            "帮我随便看看这个项目现在能不能跑然后如果有问题就帮我修一下再测一遍",
            "做你觉得最合适的 basicflow 操作",
            "顺便把 stale、预检、启动和截图都处理一下",
        ],
    }


def _project_readiness_request_catalog(project_root: Path) -> dict[str, Any]:
    intents: list[dict[str, Any]] = []
    for spec in _PROJECT_READINESS_REQUEST_SPECS:
        notes: list[str] = []
        if bool(spec.get("needs_explicit_path", False)):
            notes.append("include a full .exe path in the same request when possible")
        intents.append(
            {
                "id": str(spec.get("id", "")).strip(),
                "domain": str(spec.get("domain", "")).strip(),
                "tool": str(spec.get("tool", "")).strip(),
                "user_phrases": list(spec.get("user_phrases", [])),
                "purpose": str(spec.get("purpose", "")).strip(),
                "needs_explicit_path": bool(spec.get("needs_explicit_path", False)),
                "notes": notes,
            }
        )
    return {
        "status": "project_readiness_catalog_ready",
        "project_root": str(project_root.resolve()),
        "intents": intents,
    }


def _resolve_project_readiness_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    normalized = _normalize_user_request(user_request)
    catalog = _project_readiness_request_catalog(project_root)
    for intent in catalog["intents"]:
        phrases = intent.get("user_phrases", [])
        if isinstance(phrases, list) and _matches_basicflow_phrase(user_request, [str(item) for item in phrases]):
            tool = str(intent.get("tool", "")).strip()
            project_root_str = str(project_root.resolve())
            if tool == "configure_godot_executable":
                executable = _extract_windows_executable_path(user_request)
                if executable:
                    return {
                        "status": "project_readiness_request_resolved",
                        "resolved": True,
                        "domain": "project_readiness",
                        "tool": tool,
                        "args": {"project_root": project_root_str, "godot_executable": executable},
                        "ready_to_execute": True,
                        "ask_confirmation": False,
                        "message": "configure the requested Godot executable path for this project",
                        "matched_intent": intent,
                        "catalog": catalog,
                    }
                return {
                    "status": "project_readiness_request_resolved",
                    "resolved": True,
                    "domain": "project_readiness",
                    "tool": tool,
                    "args": {"project_root": project_root_str},
                    "ready_to_execute": False,
                    "ask_confirmation": True,
                    "message": "ask the user for a concrete Godot executable path before configuring this project",
                    "matched_intent": intent,
                    "catalog": catalog,
                }
            if tool == "preflight_project":
                return {
                    "status": "project_readiness_request_resolved",
                    "resolved": True,
                    "domain": "project_readiness",
                    "tool": tool,
                    "args": {"project_root": project_root_str},
                    "ready_to_execute": True,
                    "ask_confirmation": False,
                    "message": "run project preflight to check executable config, plugin install, runtime tmp, and UID consistency",
                    "matched_intent": intent,
                    "catalog": catalog,
                }
    return {
        "status": "no_project_readiness_request_match",
        "resolved": False,
        "domain": "",
        "tool": "",
        "args": {},
        "ready_to_execute": False,
        "ask_confirmation": False,
        "message": "the request did not match the current project-readiness phrase set",
        "catalog": catalog,
    }


def _normalize_user_request(text: str) -> str:
    normalized = str(text).strip().lower()
    for token in ('"', "'", "“", "”", "‘", "’", "，", ",", "。", ".", "！", "!", "？", "?", "：", ":", "；", ";"):
        normalized = normalized.replace(token, " ")
    return " ".join(part for part in normalized.split() if part)


def _extract_windows_executable_path(text: str) -> str:
    match = _WINDOWS_EXE_PATH_RE.search(str(text))
    if not match:
        return ""
    return str(match.group(1)).strip()


def _matches_basicflow_phrase(request_text: str, phrases: list[str]) -> bool:
    normalized_request = _normalize_user_request(request_text)
    if normalized_request == "":
        return False
    for phrase in phrases:
        normalized_phrase = _normalize_user_request(phrase)
        if normalized_phrase and normalized_phrase in normalized_request:
            return True
    return False


def _resolve_basicflow_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    intent_payload = _basicflow_user_intent_payload(project_root)
    matched_intent: dict[str, Any] | None = None
    for intent in intent_payload["intents"]:
        phrases = intent.get("user_phrases", [])
        if isinstance(phrases, list) and _matches_basicflow_phrase(user_request, [str(item) for item in phrases]):
            matched_intent = intent
            break
    if matched_intent is None:
        return {
            "status": "no_basicflow_intent_match",
            "resolved": False,
            "project_root": str(project_root.resolve()),
            "user_request": user_request,
            "tool": "",
            "reason": "the request did not match the current basicflow-related phrase set",
            "requires_confirmation": False,
            "follow_up_message": "ask a more specific basicflow request such as run, generate, or analyze basicflow",
            "known_user_phrases": [phrase for intent in intent_payload["intents"] for phrase in intent.get("user_phrases", [])],
        }
    primary = intent_payload["primary_recommendation"]
    recommended_action = primary
    if matched_intent.get("tool") == "analyze_basic_flow_staleness":
        recommended_action = {
            "id": matched_intent["id"],
            "tool": matched_intent["tool"],
            "reason": "the user explicitly asked for staleness analysis",
            "next_step": matched_intent.get("next_step", ""),
        }
    elif matched_intent.get("tool") == "generate_basic_flow":
        recommended_action = {
            "id": matched_intent["id"],
            "tool": matched_intent["tool"],
            "reason": "the user explicitly asked to generate or regenerate the basicflow asset",
            "next_step": matched_intent.get("next_step", ""),
        }
    recommended_tool = str(recommended_action.get("tool", "")).strip()
    requires_confirmation = recommended_tool == "run_basic_flow" and intent_payload["basicflow_state"] == "stale"
    follow_up_message = str(recommended_action.get("next_step", "")).strip()
    if requires_confirmation:
        follow_up_message = "the saved basicflow is stale; confirm whether to run it with allow-stale-basicflow"
    return {
        "status": "basicflow_request_resolved",
        "resolved": True,
        "project_root": str(project_root.resolve()),
        "user_request": user_request,
        "tool": recommended_tool,
        "reason": str(recommended_action.get("reason", "")).strip(),
        "requires_confirmation": requires_confirmation,
        "follow_up_message": follow_up_message,
        "matched_intent": matched_intent,
        "basicflow_state": intent_payload["basicflow_state"],
        "recommended_action": recommended_action,
        "intent_catalog": intent_payload,
    }


def _plan_basicflow_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    resolution = _resolve_basicflow_user_request(project_root, user_request)
    if not bool(resolution.get("resolved", False)):
        return {
            "status": "no_basicflow_request_plan",
            "resolved": False,
            "tool": "",
            "args": {},
            "ready_to_execute": False,
            "ask_confirmation": False,
            "message": str(resolution.get("follow_up_message", "")).strip(),
            "resolution": resolution,
        }
    resolved_tool = str(resolution.get("tool", "")).strip()
    project_root_str = str(project_root.resolve())
    ask_confirmation = bool(resolution.get("requires_confirmation", False))
    if resolved_tool == "run_basic_flow":
        args: dict[str, Any] = {"project_root": project_root_str}
        if resolution.get("basicflow_state") == "stale":
            args["allow_stale_basicflow"] = True
        return {
            "status": "basicflow_request_planned",
            "resolved": True,
            "tool": "run_basic_flow",
            "args": args,
            "ready_to_execute": not ask_confirmation,
            "ask_confirmation": ask_confirmation,
            "message": str(resolution.get("follow_up_message", "")).strip(),
            "resolution": resolution,
        }
    if resolved_tool == "analyze_basic_flow_staleness":
        return {
            "status": "basicflow_request_planned",
            "resolved": True,
            "tool": "analyze_basic_flow_staleness",
            "args": {"project_root": project_root_str},
            "ready_to_execute": True,
            "ask_confirmation": False,
            "message": str(resolution.get("follow_up_message", "")).strip(),
            "resolution": resolution,
        }
    if resolved_tool == "generate_basic_flow":
        return {
            "status": "basicflow_request_planned",
            "resolved": True,
            "tool": "get_basic_flow_generation_questions",
            "args": {"project_root": project_root_str},
            "ready_to_execute": True,
            "ask_confirmation": False,
            "message": "collect the 3 generation answers before calling generate_basic_flow",
            "follow_up_tool": "generate_basic_flow",
            "resolution": resolution,
        }
    return {
        "status": "no_basicflow_request_plan",
        "resolved": False,
        "tool": "",
        "args": {},
        "ready_to_execute": False,
        "ask_confirmation": False,
        "message": f"unsupported resolved tool for planning: {resolved_tool}",
        "resolution": resolution,
    }


def _plan_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    basicflow_plan = _plan_basicflow_user_request(project_root, user_request)
    if str(basicflow_plan.get("status", "")).strip() == "basicflow_request_planned":
        return {
            "status": "user_request_planned",
            "resolved": True,
            "domain": "basicflow",
            "tool": str(basicflow_plan.get("tool", "")).strip(),
            "args": basicflow_plan.get("args", {}),
            "ready_to_execute": bool(basicflow_plan.get("ready_to_execute", False)),
            "ask_confirmation": bool(basicflow_plan.get("ask_confirmation", False)),
            "message": str(basicflow_plan.get("message", "")).strip(),
            "plan": basicflow_plan,
        }
    readiness_resolution = _resolve_project_readiness_user_request(project_root, user_request)
    if bool(readiness_resolution.get("resolved", False)):
        return {
            "status": "user_request_planned",
            "resolved": True,
            "domain": str(readiness_resolution.get("domain", "")).strip(),
            "tool": str(readiness_resolution.get("tool", "")).strip(),
            "args": readiness_resolution.get("args", {}),
            "ready_to_execute": bool(readiness_resolution.get("ready_to_execute", False)),
            "ask_confirmation": bool(readiness_resolution.get("ask_confirmation", False)),
            "message": str(readiness_resolution.get("message", "")).strip(),
            "plan": readiness_resolution,
        }
    return {
        "status": "no_user_request_plan",
        "resolved": False,
        "domain": "",
        "tool": "",
        "args": {},
        "ready_to_execute": False,
        "ask_confirmation": False,
        "message": "no supported high-level request planner matched the current user request",
        "basicflow_plan": basicflow_plan,
    }


def _handle_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    plan = _plan_user_request(project_root, user_request)
    if not bool(plan.get("resolved", False)):
        return {
            "status": "no_user_request_handler",
            "resolved": False,
            "ready_to_execute": False,
            "tool": "",
            "args": {},
            "message": str(plan.get("message", "")).strip(),
            "plan": plan,
        }
    if not bool(plan.get("ready_to_execute", False)):
        return {
            "status": "user_request_needs_input",
            "resolved": True,
            "ready_to_execute": False,
            "tool": str(plan.get("tool", "")).strip(),
            "args": plan.get("args", {}),
            "ask_confirmation": bool(plan.get("ask_confirmation", False)),
            "message": str(plan.get("message", "")).strip(),
            "plan": plan,
        }
    tool = str(plan.get("tool", "")).strip()
    if tool == "preflight_project":
        result = run_preflight(project_root)
        return {
            "status": "user_request_handled",
            "resolved": True,
            "executed": True,
            "domain": str(plan.get("domain", "")).strip(),
            "tool": tool,
            "args": plan.get("args", {}),
            "message": str(plan.get("message", "")).strip(),
            "result": result.to_dict(),
            "plan": plan,
        }
    if tool == "configure_godot_executable":
        executable = str(plan.get("args", {}).get("godot_executable", "")).strip()
        if not executable:
            return {
                "status": "user_request_needs_input",
                "resolved": True,
                "ready_to_execute": False,
                "tool": tool,
                "args": plan.get("args", {}),
                "ask_confirmation": True,
                "message": "ask the user for a concrete Godot executable path before configuring this project",
                "plan": plan,
            }
        target = configure_godot_executable(project_root, executable)
        return {
            "status": "user_request_handled",
            "resolved": True,
            "executed": True,
            "domain": str(plan.get("domain", "")).strip(),
            "tool": tool,
            "args": plan.get("args", {}),
            "message": str(plan.get("message", "")).strip(),
            "result": {"status": "configured", "config_file": str(target)},
            "plan": plan,
        }
    if tool == "get_basic_flow_generation_questions":
        follow_up_tool = str(plan.get("follow_up_tool", "")).strip()
        if not follow_up_tool:
            nested_plan = plan.get("plan", {})
            if isinstance(nested_plan, dict):
                follow_up_tool = str(nested_plan.get("follow_up_tool", "")).strip()
        return {
            "status": "user_request_handled",
            "resolved": True,
            "executed": True,
            "domain": str(plan.get("domain", "")).strip(),
            "tool": tool,
            "args": plan.get("args", {}),
            "message": str(plan.get("message", "")).strip(),
            "result": get_basicflow_generation_questions(project_root),
            "follow_up_tool": follow_up_tool,
            "plan": plan,
        }
    if tool == "analyze_basic_flow_staleness":
        return {
            "status": "user_request_handled",
            "resolved": True,
            "executed": True,
            "domain": str(plan.get("domain", "")).strip(),
            "tool": tool,
            "args": plan.get("args", {}),
            "message": str(plan.get("message", "")).strip(),
            "result": analyze_basicflow_staleness(project_root),
            "plan": plan,
        }
    return {
        "status": "user_request_not_executable",
        "resolved": True,
        "ready_to_execute": False,
        "tool": tool,
        "args": plan.get("args", {}),
        "message": f"planned tool is not yet auto-executable via handle_user_request: {tool}",
        "plan": plan,
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
                execution_mode=_normalize_execution_mode(getattr(args, "execution_mode", "play_mode")),
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

        if args.tool == "get_basic_flow_user_intents":
            _ok(_basicflow_user_intent_payload(project_root))
            return 0

        if args.tool == "get_user_request_command_guide":
            _ok(_user_request_command_guide(project_root))
            return 0

        if args.tool == "resolve_basic_flow_user_request":
            if not args.user_request:
                raise ValueError("--user-request is required")
            _ok(_resolve_basicflow_user_request(project_root, str(args.user_request)))
            return 0

        if args.tool == "plan_basic_flow_user_request":
            if not args.user_request:
                raise ValueError("--user-request is required")
            _ok(_plan_basicflow_user_request(project_root, str(args.user_request)))
            return 0

        if args.tool == "plan_user_request":
            if not args.user_request:
                raise ValueError("--user-request is required")
            _ok(_plan_user_request(project_root, str(args.user_request)))
            return 0

        if args.tool == "handle_user_request":
            if not args.user_request:
                raise ValueError("--user-request is required")
            handled = _handle_user_request(project_root, str(args.user_request))
            _ok(handled)
            result = handled.get("result")
            if isinstance(result, dict) and "ok" in result:
                return 0 if bool(result.get("ok", False)) else 2
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
