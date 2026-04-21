from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from .contracts import (
    ERR_BASICFLOW_GENERATION_ANSWERS_REQUIRED,
    ERR_BASICFLOW_GENERATION_SESSION_INCOMPLETE,
    ERR_BASICFLOW_GENERATION_SESSION_INVALID,
    ERR_BASICFLOW_GENERATION_SESSION_NOT_FOUND,
    ERR_BUG_REPORT_INCOMPLETE,
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
from .bug_analysis import analyze_bug_report
from .bug_fix_application import apply_bug_fix
from .bug_assertions import define_bug_assertions
from .bug_fix_planning import plan_bug_fix
from .bug_repro_execution import run_bug_repro_flow
from .bug_repro_flow import plan_bug_repro_flow
from .bug_report import collect_bug_report
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
from .request_layer import (
    basicflow_user_intent_payload,
    handle_user_request,
    plan_basicflow_user_request,
    plan_user_request,
    project_readiness_request_catalog,
    resolve_basicflow_user_request,
    resolve_project_readiness_user_request,
    user_request_command_guide,
)
from .runtime_orchestration import (
    acquire_flow_lock as runtime_acquire_flow_lock,
    basicflow_missing_payload as runtime_basicflow_missing_payload,
    basicflow_stale_payload as runtime_basicflow_stale_payload,
    bridge_dir as runtime_bridge_dir,
    default_plugin_source as runtime_default_plugin_source,
    detect_multiple_project_processes as runtime_detect_multiple_project_processes,
    ensure_play_mode as runtime_ensure_play_mode,
    flow_requests_close as runtime_flow_requests_close,
    flow_lock_path as runtime_flow_lock_path,
    is_editor_process_running as runtime_is_editor_process_running,
    is_pid_running as runtime_is_pid_running,
    launch_editor_if_needed as runtime_launch_editor_if_needed,
    list_project_editor_processes as runtime_list_project_editor_processes,
    list_project_processes as runtime_list_project_processes,
    normalize_execution_mode as runtime_normalize_execution_mode,
    read_flow_lock as runtime_read_flow_lock,
    read_runtime_gate as runtime_read_runtime_gate,
    release_flow_lock as runtime_release_flow_lock,
    request_auto_enter_play as runtime_request_auto_enter_play,
    resolve_requested_flow_file as runtime_resolve_requested_flow_file,
    run_basic_flow_tool as runtime_run_basic_flow_tool,
    runtime_gate_path as runtime_runtime_gate_path,
    clear_runtime_markers as runtime_clear_runtime_markers,
    terminate_project_processes as runtime_terminate_project_processes,
    verify_teardown as runtime_verify_teardown,
)
from .tool_dispatch import ToolDispatchApi, dispatch_tool
from .windows_isolated_runtime import (
    close_isolated_runtime_session,
    launch_isolated_runtime,
    verify_isolated_runtime_stopped,
)


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
    parser.add_argument("--bug-report")
    parser.add_argument("--bug-summary")
    parser.add_argument("--expected-behavior")
    parser.add_argument("--steps-to-trigger")
    parser.add_argument("--location-scene")
    parser.add_argument("--location-node")
    parser.add_argument("--location-script")
    parser.add_argument("--frequency-hint")
    parser.add_argument("--severity-hint")
    return parser.parse_args()


def _ok(result: dict[str, Any]) -> None:
    print(json.dumps(build_ok_payload(result), ensure_ascii=False))


def _err(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    print(json.dumps(build_error_payload(code, message, details), ensure_ascii=False))


def _bridge_dir(project_root: Path) -> Path:
    return runtime_bridge_dir(project_root)


def _runtime_gate_path(project_root: Path) -> Path:
    return runtime_runtime_gate_path(project_root)


def _default_plugin_source() -> Path:
    return runtime_default_plugin_source(__file__)


def _sync_project_plugin(project_root: Path) -> Path:
    return sync_plugin(_default_plugin_source(), project_root)


def _flow_lock_path(project_root: Path) -> Path:
    return runtime_flow_lock_path(project_root)


def _normalize_execution_mode(raw: str | None) -> str:
    return runtime_normalize_execution_mode(raw)


def _read_runtime_gate(project_root: Path) -> dict[str, Any]:
    return runtime_read_runtime_gate(project_root)


def _list_project_processes(project_root: Path) -> list[dict[str, Any]]:
    return runtime_list_project_processes(project_root, subprocess_run=subprocess.run)


def _is_pid_running(pid: int) -> bool:
    return runtime_is_pid_running(pid, subprocess_run=subprocess.run)


def _is_editor_process_running(project_root: Path) -> bool:
    return runtime_is_editor_process_running(
        project_root,
        list_project_editor_processes=_list_project_editor_processes,
    )


def _list_project_editor_processes(project_root: Path) -> list[dict[str, Any]]:
    return runtime_list_project_editor_processes(
        project_root,
        list_project_processes=_list_project_processes,
    )


def _request_auto_enter_play(project_root: Path) -> Path:
    return runtime_request_auto_enter_play(project_root)


def _launch_editor_if_needed(project_root: Path, timeout_ms: int = 12000) -> dict[str, Any]:
    return runtime_launch_editor_if_needed(
        project_root,
        load_godot_executable=load_godot_executable,
        is_editor_process_running=_is_editor_process_running,
        read_runtime_gate=_read_runtime_gate,
        subprocess_popen=subprocess.Popen,
        monotonic=time.monotonic,
        sleep=time.sleep,
        timeout_ms=timeout_ms,
    )


def _ensure_play_mode(project_root: Path, timeout_ms: int = 15000) -> dict[str, Any]:
    return runtime_ensure_play_mode(
        project_root,
        launch_editor_if_needed=lambda path: _launch_editor_if_needed(path, timeout_ms=12000),
        is_editor_process_running=_is_editor_process_running,
        read_runtime_gate=_read_runtime_gate,
        request_auto_enter_play=_request_auto_enter_play,
        monotonic=time.monotonic,
        sleep=time.sleep,
        timeout_ms=timeout_ms,
    )


def _flow_requests_close(flow_payload: dict[str, Any]) -> bool:
    return runtime_flow_requests_close(flow_payload)


def _verify_teardown(project_root: Path, timeout_ms: int = 10000, *, stable_ms: int = 500) -> dict[str, Any]:
    return runtime_verify_teardown(
        project_root,
        read_runtime_gate=_read_runtime_gate,
        list_project_processes=_list_project_processes,
        monotonic=time.monotonic,
        sleep=time.sleep,
        timeout_ms=timeout_ms,
        stable_ms=stable_ms,
    )


def _terminate_project_processes(project_root: Path) -> dict[str, Any]:
    return runtime_terminate_project_processes(
        project_root,
        list_project_processes=_list_project_processes,
        subprocess_run=subprocess.run,
        sleep=time.sleep,
    )


def _clear_runtime_markers(project_root: Path) -> None:
    runtime_clear_runtime_markers(project_root)


def _read_flow_lock(project_root: Path) -> dict[str, Any]:
    return runtime_read_flow_lock(project_root)


def _detect_multiple_project_processes(project_root: Path) -> dict[str, Any] | None:
    return runtime_detect_multiple_project_processes(
        project_root,
        list_project_editor_processes=_list_project_editor_processes,
    )


def _release_flow_lock(project_root: Path, token: str) -> None:
    runtime_release_flow_lock(
        project_root,
        token,
        read_flow_lock=_read_flow_lock,
    )


def _acquire_flow_lock(project_root: Path) -> dict[str, Any]:
    return runtime_acquire_flow_lock(
        project_root,
        read_flow_lock=_read_flow_lock,
        is_pid_running=_is_pid_running,
    )


def _run_basic_flow_tool(
    project_root: Path,
    flow_file: Path,
    *,
    basicflow_context: dict[str, Any] | None = None,
    execution_mode: str = "play_mode",
) -> tuple[int, dict[str, Any], bool]:
    return runtime_run_basic_flow_tool(
        project_root,
        flow_file,
        basicflow_context=basicflow_context,
        execution_mode=execution_mode,
        load_flow=load_flow,
        sync_project_plugin=_sync_project_plugin,
        run_preflight=run_preflight,
        detect_multiple_project_processes=_detect_multiple_project_processes,
        acquire_flow_lock=_acquire_flow_lock,
        ensure_play_mode=_ensure_play_mode,
        launch_isolated_runtime=launch_isolated_runtime,
        load_godot_executable=load_godot_executable,
        run_basic_flow=run_basic_flow,
        verify_isolated_runtime_stopped=verify_isolated_runtime_stopped,
        verify_teardown=lambda path: _verify_teardown(path),
        terminate_project_processes=_terminate_project_processes,
        clear_runtime_markers=_clear_runtime_markers,
        mark_basicflow_run_success=mark_basicflow_run_success,
        basicflow_paths=basicflow_paths,
        close_isolated_runtime_session=close_isolated_runtime_session,
        release_flow_lock=_release_flow_lock,
    )


def _basicflow_missing_payload(project_root: Path) -> dict[str, Any]:
    return runtime_basicflow_missing_payload(project_root)


def _basicflow_stale_payload(project_root: Path, stale_result: dict[str, Any]) -> dict[str, Any]:
    return runtime_basicflow_stale_payload(project_root, stale_result)


def _resolve_requested_flow_file(
    project_root: Path,
    flow_file_arg: str | None,
    *,
    allow_stale_basicflow: bool,
) -> tuple[Path | None, dict[str, Any] | None, dict[str, Any] | None]:
    return runtime_resolve_requested_flow_file(
        project_root,
        flow_file_arg,
        allow_stale_basicflow=allow_stale_basicflow,
        detect_basicflow_staleness=detect_basicflow_staleness,
        load_basicflow_assets=load_basicflow_assets,
    )


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
    return basicflow_user_intent_payload(
        project_root,
        detect_basicflow_staleness=detect_basicflow_staleness,
    )


def _user_request_command_guide(project_root: Path) -> dict[str, Any]:
    return user_request_command_guide(
        project_root,
        detect_basicflow_staleness=detect_basicflow_staleness,
    )


def _project_readiness_request_catalog(project_root: Path) -> dict[str, Any]:
    return project_readiness_request_catalog(project_root)


def _resolve_project_readiness_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    return resolve_project_readiness_user_request(project_root, user_request)


def _resolve_basicflow_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    return resolve_basicflow_user_request(
        project_root,
        user_request,
        detect_basicflow_staleness=detect_basicflow_staleness,
    )


def _plan_basicflow_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    return plan_basicflow_user_request(
        project_root,
        user_request,
        detect_basicflow_staleness=detect_basicflow_staleness,
    )


def _plan_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    return plan_user_request(
        project_root,
        user_request,
        detect_basicflow_staleness=detect_basicflow_staleness,
    )


def _handle_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    return handle_user_request(
        project_root,
        user_request,
        detect_basicflow_staleness=detect_basicflow_staleness,
        run_preflight=run_preflight,
        configure_godot_executable=configure_godot_executable,
        get_basicflow_generation_questions=get_basicflow_generation_questions,
        analyze_basicflow_staleness=analyze_basicflow_staleness,
    )


def _build_tool_dispatch_api() -> ToolDispatchApi:
    return ToolDispatchApi(
        collect_bug_report=collect_bug_report,
        analyze_bug_report=analyze_bug_report,
        define_bug_assertions=define_bug_assertions,
        plan_bug_repro_flow=plan_bug_repro_flow,
        run_bug_repro_flow=lambda project_root, args, execution_mode: run_bug_repro_flow(
            project_root,
            args,
            run_basic_flow_tool=lambda root, flow_file, basicflow_context, mode: _run_basic_flow_tool(
                root,
                flow_file,
                basicflow_context=basicflow_context,
                execution_mode=mode,
            ),
            normalize_execution_mode=lambda _: execution_mode,
        ),
        plan_bug_fix=lambda project_root, args: plan_bug_fix(
            project_root,
            args,
            run_bug_repro_flow_fn=lambda root, inner_args: run_bug_repro_flow(
                root,
                inner_args,
                run_basic_flow_tool=lambda sub_root, flow_file, basicflow_context, mode: _run_basic_flow_tool(
                    sub_root,
                    flow_file,
                    basicflow_context=basicflow_context,
                    execution_mode=mode,
                ),
                normalize_execution_mode=_normalize_execution_mode,
            ),
        ),
        apply_bug_fix=lambda project_root, args: apply_bug_fix(
            project_root,
            args,
            plan_bug_fix_fn=lambda root, inner_args: plan_bug_fix(
                root,
                inner_args,
                run_bug_repro_flow_fn=lambda repro_root, repro_args: run_bug_repro_flow(
                    repro_root,
                    repro_args,
                    run_basic_flow_tool=lambda sub_root, flow_file, basicflow_context, mode: _run_basic_flow_tool(
                        sub_root,
                        flow_file,
                        basicflow_context=basicflow_context,
                        execution_mode=mode,
                    ),
                    normalize_execution_mode=_normalize_execution_mode,
                ),
            ),
        ),
        configure_godot_executable=configure_godot_executable,
        sync_project_plugin=_sync_project_plugin,
        run_preflight=run_preflight,
        resolve_requested_flow_file=lambda project_root, flow_file_arg, allow_stale_basicflow: _resolve_requested_flow_file(
            project_root,
            flow_file_arg,
            allow_stale_basicflow=allow_stale_basicflow,
        ),
        run_basic_flow_tool=lambda project_root, flow_file, basicflow_context, execution_mode: _run_basic_flow_tool(
            project_root,
            flow_file,
            basicflow_context=basicflow_context,
            execution_mode=execution_mode,
        ),
        normalize_execution_mode=_normalize_execution_mode,
        collect_inline_generation_answers=_collect_inline_generation_answers,
        generate_basicflow_from_answers_file=generate_basicflow_from_answers_file,
        generate_basicflow_from_answers=generate_basicflow_from_answers,
        get_basicflow_generation_questions=get_basicflow_generation_questions,
        get_basicflow_user_intents=_basicflow_user_intent_payload,
        get_user_request_command_guide=_user_request_command_guide,
        resolve_basicflow_user_request=_resolve_basicflow_user_request,
        plan_basicflow_user_request=_plan_basicflow_user_request,
        plan_user_request=_plan_user_request,
        handle_user_request=_handle_user_request,
        start_basicflow_generation_session=start_basicflow_generation_session,
        answer_basicflow_generation_session=lambda project_root, session_id, question_id, answer: answer_basicflow_generation_session(
            project_root,
            session_id=session_id,
            question_id=question_id,
            answer=answer,
        ),
        complete_basicflow_generation_session=lambda project_root, session_id: complete_basicflow_generation_session(
            project_root,
            session_id=session_id,
        ),
        analyze_basicflow_staleness=analyze_basicflow_staleness,
    )


def main() -> int:
    args = _parse_args()
    project_root = Path(args.project_root)
    try:
        exit_code, payload = dispatch_tool(args, project_root, _build_tool_dispatch_api())
        print(json.dumps(payload, ensure_ascii=False))
        return exit_code
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
