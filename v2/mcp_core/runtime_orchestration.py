from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .contracts import (
    ERR_BASICFLOW_MISSING,
    ERR_BASICFLOW_STALE,
    ERR_ENGINE_RUNTIME_STALLED,
    ERR_FLOW_ALREADY_RUNNING,
    ERR_MULTIPLE_EDITOR_PROCESSES_DETECTED,
    ERR_PREFLIGHT_FAILED,
    ERR_STEP_FAILED,
    ERR_TEARDOWN_VERIFICATION_FAILED,
    ERR_TIMEOUT,
    build_error_payload,
    build_ok_payload,
)
from .flow_runner import FlowExecutionEngineStalled, FlowExecutionStepFailed, FlowExecutionTimeout
from .process_probe import (
    detect_multiple_project_processes as probe_detect_multiple_project_processes,
    is_editor_process_running as probe_is_editor_process_running,
    is_pid_running as probe_is_pid_running,
    list_project_editor_processes as probe_list_project_editor_processes,
    list_project_processes as probe_list_project_processes,
    terminate_project_processes as probe_terminate_project_processes,
)
from .teardown_verification import (
    acquire_flow_lock as teardown_acquire_flow_lock,
    flow_lock_path as teardown_flow_lock_path,
    read_flow_lock as teardown_read_flow_lock,
    release_flow_lock as teardown_release_flow_lock,
    verify_teardown as teardown_verify_teardown,
)

SUPPORTED_EXECUTION_MODES = {"play_mode", "isolated_runtime"}


def bridge_dir(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp").resolve()


def runtime_gate_path(project_root: Path) -> Path:
    return bridge_dir(project_root) / "runtime_gate.json"


def default_plugin_source(module_file: str) -> Path:
    return Path(module_file).resolve().parents[1] / "godot_plugin" / "addons" / "pointer_gpf"


def flow_lock_path(project_root: Path) -> Path:
    return teardown_flow_lock_path(bridge_dir, project_root)


def normalize_execution_mode(raw: str | None) -> str:
    mode = str(raw or "play_mode").strip().lower()
    if mode not in SUPPORTED_EXECUTION_MODES:
        supported = ", ".join(sorted(SUPPORTED_EXECUTION_MODES))
        raise ValueError(f"unsupported execution mode: {raw!r}; supported values: {supported}")
    return mode


def read_runtime_gate(project_root: Path) -> dict[str, Any]:
    gate_path = runtime_gate_path(project_root)
    if not gate_path.is_file():
        return {}
    try:
        data = json.loads(gate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def list_project_processes(
    project_root: Path,
    *,
    subprocess_run: Callable[..., Any] = subprocess.run,
) -> list[dict[str, Any]]:
    return probe_list_project_processes(project_root, subprocess_run=subprocess_run)


def is_pid_running(
    pid: int,
    *,
    subprocess_run: Callable[..., Any] = subprocess.run,
) -> bool:
    return probe_is_pid_running(pid, subprocess_run=subprocess_run)


def list_project_editor_processes(
    project_root: Path,
    *,
    list_project_processes: Callable[[Path], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return probe_list_project_editor_processes(project_root, list_project_processes=list_project_processes)


def is_editor_process_running(
    project_root: Path,
    *,
    list_project_editor_processes: Callable[[Path], list[dict[str, Any]]],
) -> bool:
    return probe_is_editor_process_running(project_root, list_project_editor_processes=list_project_editor_processes)


def terminate_project_processes(
    project_root: Path,
    *,
    list_project_processes: Callable[[Path], list[dict[str, Any]]],
    subprocess_run: Callable[..., Any] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    return probe_terminate_project_processes(
        project_root,
        list_project_processes=list_project_processes,
        subprocess_run=subprocess_run,
        sleep=sleep,
    )


def request_auto_enter_play(project_root: Path) -> Path:
    target = bridge_dir(project_root) / "auto_enter_play_mode.flag"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"schema": "pointer_gpf.v2.auto_enter.v1"}), encoding="utf-8")
    return target


def launch_editor_if_needed(
    project_root: Path,
    *,
    load_godot_executable: Callable[[Path], str],
    is_editor_process_running: Callable[[Path], bool],
    read_runtime_gate: Callable[[Path], dict[str, Any]],
    subprocess_popen: Callable[..., Any] = subprocess.Popen,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    timeout_ms: int = 12000,
) -> dict[str, Any]:
    gate_path = runtime_gate_path(project_root)
    if is_editor_process_running(project_root):
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
    subprocess_popen([executable, "-e", "--path", str(project_root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = monotonic() + max(1, timeout_ms) / 1000.0
    while monotonic() < deadline:
        if gate_path.is_file():
            data = read_runtime_gate(project_root)
            if isinstance(data, dict):
                return {"status": "launched_editor", "runtime_gate": data}
        sleep(0.05)
    raise TimeoutError(f"editor bridge was not ready within {timeout_ms} ms")


def ensure_play_mode(
    project_root: Path,
    *,
    launch_editor_if_needed: Callable[[Path], dict[str, Any]],
    is_editor_process_running: Callable[[Path], bool],
    read_runtime_gate: Callable[[Path], dict[str, Any]],
    request_auto_enter_play: Callable[[Path], Path],
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    timeout_ms: int = 15000,
) -> dict[str, Any]:
    launch_meta = launch_editor_if_needed(project_root)
    gate_path = runtime_gate_path(project_root)
    if gate_path.is_file() and is_editor_process_running(project_root):
        data = read_runtime_gate(project_root)
        if isinstance(data, dict) and bool(data.get("runtime_gate_passed", False)):
            return {"status": "already_running", "runtime_gate": data, "editor_bridge": launch_meta}
    request_auto_enter_play(project_root)
    deadline = monotonic() + max(1, timeout_ms) / 1000.0
    while monotonic() < deadline:
        if gate_path.is_file():
            data = read_runtime_gate(project_root)
            if isinstance(data, dict) and bool(data.get("runtime_gate_passed", False)):
                return {"status": "entered_play_mode", "runtime_gate": data, "editor_bridge": launch_meta}
        sleep(0.05)
    raise TimeoutError(f"play mode was not entered within {timeout_ms} ms")


def flow_requests_close(flow_payload: dict[str, Any]) -> bool:
    steps = flow_payload.get("steps", [])
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("action", "")).strip().lower() == "closeproject":
            return True
    return False


def verify_teardown(
    project_root: Path,
    *,
    read_runtime_gate: Callable[[Path], dict[str, Any]],
    list_project_processes: Callable[[Path], list[dict[str, Any]]],
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    timeout_ms: int = 10000,
    stable_ms: int = 500,
) -> dict[str, Any]:
    return teardown_verify_teardown(
        project_root,
        read_runtime_gate=read_runtime_gate,
        list_project_processes=list_project_processes,
        monotonic=monotonic,
        sleep=sleep,
        timeout_ms=timeout_ms,
        stable_ms=stable_ms,
    )


def clear_runtime_markers(project_root: Path) -> None:
    for name in (
        "runtime_gate.json",
        "runtime_session.json",
        "auto_enter_play_mode.flag",
        "auto_stop_play_mode.flag",
        "command.json",
        "response.json",
    ):
        (bridge_dir(project_root) / name).unlink(missing_ok=True)


def force_cleanup_project_runtime(
    project_root: Path,
    *,
    terminate_project_processes: Callable[[Path], dict[str, Any]],
    clear_runtime_markers: Callable[[Path], None],
    verify_teardown: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    termination = terminate_project_processes(project_root)
    clear_runtime_markers(project_root)
    teardown = verify_teardown(project_root)
    teardown["forced_process_cleanup"] = termination
    return teardown


def read_flow_lock(project_root: Path) -> dict[str, Any]:
    return teardown_read_flow_lock(project_root, flow_lock_path=flow_lock_path)


def detect_multiple_project_processes(
    project_root: Path,
    *,
    list_project_editor_processes: Callable[[Path], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    return probe_detect_multiple_project_processes(
        project_root,
        list_project_editor_processes=list_project_editor_processes,
    )


def release_flow_lock(project_root: Path, token: str, *, read_flow_lock: Callable[[Path], dict[str, Any]]) -> None:
    teardown_release_flow_lock(
        project_root,
        token,
        flow_lock_path=flow_lock_path,
        read_flow_lock=read_flow_lock,
    )


def acquire_flow_lock(
    project_root: Path,
    *,
    read_flow_lock: Callable[[Path], dict[str, Any]],
    is_pid_running: Callable[[int], bool],
) -> dict[str, Any]:
    return teardown_acquire_flow_lock(
        project_root,
        flow_lock_path=flow_lock_path,
        read_flow_lock=read_flow_lock,
        is_pid_running=is_pid_running,
    )


def basicflow_missing_payload(project_root: Path) -> dict[str, Any]:
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


def basicflow_stale_payload(project_root: Path, stale_result: dict[str, Any]) -> dict[str, Any]:
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


def resolve_requested_flow_file(
    project_root: Path,
    flow_file_arg: str | None,
    *,
    allow_stale_basicflow: bool,
    detect_basicflow_staleness: Callable[[Path], dict[str, Any]],
    load_basicflow_assets: Callable[[Path], dict[str, Any]],
) -> tuple[Path | None, dict[str, Any] | None, dict[str, Any] | None]:
    if flow_file_arg:
        return Path(flow_file_arg), None, None
    stale_result = detect_basicflow_staleness(project_root)
    if stale_result["status"] == "missing":
        return None, basicflow_missing_payload(project_root), None
    if stale_result["status"] == "stale":
        if not allow_stale_basicflow:
            return None, basicflow_stale_payload(project_root, stale_result), None
        assets = load_basicflow_assets(project_root)
        return Path(assets["paths"]["flow_file"]), None, stale_result
    assets = load_basicflow_assets(project_root)
    return Path(assets["paths"]["flow_file"]), None, stale_result


def run_basic_flow_tool(
    project_root: Path,
    flow_file: Path,
    *,
    basicflow_context: dict[str, Any] | None = None,
    execution_mode: str = "play_mode",
    load_flow: Callable[[Path], dict[str, Any]],
    sync_project_plugin: Callable[[Path], Path],
    run_preflight: Callable[[Path], Any],
    detect_multiple_project_processes: Callable[[Path], dict[str, Any] | None],
    acquire_flow_lock: Callable[[Path], dict[str, Any]],
    ensure_play_mode: Callable[[Path], dict[str, Any]],
    launch_isolated_runtime: Callable[[Path, str], Any],
    load_godot_executable: Callable[[Path], str],
    run_basic_flow: Callable[[Path, Path], dict[str, Any]],
    verify_isolated_runtime_stopped: Callable[[Any], dict[str, Any]],
    verify_teardown: Callable[[Path], dict[str, Any]],
    terminate_project_processes: Callable[[Path], dict[str, Any]],
    clear_runtime_markers: Callable[[Path], None],
    mark_basicflow_run_success: Callable[[Path], dict[str, Any]],
    basicflow_paths: Callable[[Path], Any],
    close_isolated_runtime_session: Callable[[Any], None],
    release_flow_lock: Callable[[Path, str], None],
) -> tuple[int, dict[str, Any], bool]:
    execution_mode = normalize_execution_mode(execution_mode)
    flow_payload = load_flow(flow_file)
    flow_lock: dict[str, Any] | None = None
    isolated_session = None
    plugin_destination = sync_project_plugin(project_root)
    result = run_preflight(project_root)
    if not result.ok:
        return 2, build_error_payload(ERR_PREFLIGHT_FAILED, "project preflight failed", result.to_dict()), False
    multi_editor = detect_multiple_project_processes(project_root) if execution_mode == "play_mode" else None
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
        flow_lock = acquire_flow_lock(project_root)
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
        response_payload: dict[str, Any] | None = None
        exit_code = 2
        mark_success = False
        play_session_started = False
        teardown_meta: dict[str, Any] | None = None
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
            play_session_started = True
            try:
                play_meta = ensure_play_mode(project_root)
            except TimeoutError as exc:
                teardown_meta = force_cleanup_project_runtime(
                    project_root,
                    terminate_project_processes=terminate_project_processes,
                    clear_runtime_markers=clear_runtime_markers,
                    verify_teardown=verify_teardown,
                )
                return (
                    2,
                    build_error_payload(
                        ERR_TIMEOUT,
                        str(exc),
                        {"project_close": teardown_meta},
                    ),
                    False,
                )
            play_meta["execution_mode"] = execution_mode
        try:
            run_result = run_basic_flow(project_root, flow_file)
        except FlowExecutionStepFailed as exc:
            response_payload = build_error_payload(
                ERR_STEP_FAILED,
                str(exc),
                {"run_id": exc.run_id, "step_index": exc.step_index, "step_id": exc.step_id, "play_mode": play_meta},
            )
        except FlowExecutionTimeout as exc:
            response_payload = build_error_payload(
                ERR_TIMEOUT,
                str(exc),
                {"run_id": exc.run_id, "step_index": exc.step_index, "step_id": exc.step_id, "play_mode": play_meta},
            )
        except FlowExecutionEngineStalled as exc:
            response_payload = build_error_payload(
                ERR_ENGINE_RUNTIME_STALLED,
                str(exc),
                {
                    "run_id": exc.run_id,
                    "step_index": exc.step_index,
                    "step_id": exc.step_id,
                    "runtime_diagnostics": exc.diagnostics,
                    "play_mode": play_meta,
                },
            )
        else:
            if flow_requests_close(flow_payload) and execution_mode == "isolated_runtime" and isolated_session is not None:
                teardown_meta = verify_isolated_runtime_stopped(isolated_session)
                if teardown_meta["status"] != "verified":
                    response_payload = build_error_payload(
                        ERR_TEARDOWN_VERIFICATION_FAILED,
                        "play mode did not fully stop after closeProject",
                        {"play_mode": play_meta, "execution": run_result, "project_close": teardown_meta},
                    )
            if response_payload is None:
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
                    "runtime_evidence_records": run_result.get("runtime_evidence_records", [])
                    if isinstance(run_result.get("runtime_evidence_records", []), list)
                    else [],
                    "runtime_evidence_summary": run_result.get("runtime_evidence_summary", {})
                    if isinstance(run_result.get("runtime_evidence_summary", {}), dict)
                    else {},
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
                response_payload = build_ok_payload(payload)
                exit_code = 0
                mark_success = True
        if execution_mode == "play_mode" and play_session_started:
            teardown_meta = force_cleanup_project_runtime(
                project_root,
                terminate_project_processes=terminate_project_processes,
                clear_runtime_markers=clear_runtime_markers,
                verify_teardown=verify_teardown,
            )
            if response_payload is None:
                response_payload = build_error_payload(
                    ERR_TEARDOWN_VERIFICATION_FAILED,
                    "play mode run ended without a response payload",
                    {"project_close": teardown_meta},
                )
            elif response_payload.get("ok"):
                response_payload.setdefault("result", {})
                response_payload["result"]["project_close"] = teardown_meta
            else:
                response_payload.setdefault("error", {}).setdefault("details", {})
                response_payload["error"]["details"]["project_close"] = teardown_meta
            if teardown_meta["status"] != "verified":
                if response_payload.get("ok"):
                    response_payload = build_error_payload(
                        ERR_TEARDOWN_VERIFICATION_FAILED,
                        "play mode did not fully stop after the flow ended",
                        {"play_mode": play_meta, "project_close": teardown_meta},
                    )
                exit_code = 2
                mark_success = False
        assert response_payload is not None
        return exit_code, response_payload, mark_success
    finally:
        if isolated_session is not None:
            close_isolated_runtime_session(isolated_session)
        if flow_lock is not None:
            release_flow_lock(project_root, str(flow_lock.get("token", "")))
