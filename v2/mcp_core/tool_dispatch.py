from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .contracts import (
    ERR_BASICFLOW_GENERATION_ANSWERS_REQUIRED,
    ERR_BUG_REPORT_INCOMPLETE,
    ERR_UNKNOWN_TOOL,
    build_error_payload,
    build_ok_payload,
)


@dataclass(frozen=True)
class ToolDispatchApi:
    collect_bug_report: Callable[[Path, Any], dict[str, Any]]
    analyze_bug_report: Callable[[Path, Any], dict[str, Any]]
    define_bug_assertions: Callable[[Path, Any], dict[str, Any]]
    plan_bug_repro_flow: Callable[[Path, Any], dict[str, Any]]
    run_bug_repro_flow: Callable[[Path, Any, str], dict[str, Any]]
    rerun_bug_repro_flow: Callable[[Path, Any, str], dict[str, Any]]
    plan_bug_fix: Callable[[Path, Any], dict[str, Any]]
    apply_bug_fix: Callable[[Path, Any], dict[str, Any]]
    run_bug_fix_regression: Callable[[Path], dict[str, Any]]
    verify_bug_fix: Callable[[Path, Any], dict[str, Any]]
    configure_godot_executable: Callable[[Path, str], Path]
    sync_project_plugin: Callable[[Path], Path]
    run_preflight: Callable[[Path], Any]
    resolve_requested_flow_file: Callable[[Path, str | None, bool], tuple[Path | None, dict[str, Any] | None, dict[str, Any] | None]]
    run_basic_flow_tool: Callable[[Path, Path, dict[str, Any] | None, str], tuple[int, dict[str, Any], bool]]
    normalize_execution_mode: Callable[[str | None], str]
    collect_inline_generation_answers: Callable[[Any], dict[str, Any] | None]
    generate_basicflow_from_answers_file: Callable[[Path, Path], dict[str, Any]]
    generate_basicflow_from_answers: Callable[[Path, dict[str, Any]], dict[str, Any]]
    get_basicflow_generation_questions: Callable[[Path], dict[str, Any]]
    get_basicflow_user_intents: Callable[[Path], dict[str, Any]]
    get_user_request_command_guide: Callable[[Path], dict[str, Any]]
    resolve_basicflow_user_request: Callable[[Path, str], dict[str, Any]]
    plan_basicflow_user_request: Callable[[Path, str], dict[str, Any]]
    plan_user_request: Callable[[Path, str], dict[str, Any]]
    handle_user_request: Callable[[Path, str], dict[str, Any]]
    start_basicflow_generation_session: Callable[[Path], dict[str, Any]]
    answer_basicflow_generation_session: Callable[[Path, str, str, str], dict[str, Any]]
    complete_basicflow_generation_session: Callable[[Path, str], dict[str, Any]]
    analyze_basicflow_staleness: Callable[[Path], dict[str, Any]]


def dispatch_tool(args: Any, project_root: Path, api: ToolDispatchApi) -> tuple[int, dict[str, Any]]:
    if args.tool == "collect_bug_report":
        try:
            return 0, build_ok_payload(api.collect_bug_report(project_root, args))
        except ValueError as exc:
            return 2, build_error_payload(
                ERR_BUG_REPORT_INCOMPLETE,
                str(exc),
                {
                    "required_args": [
                        "--bug-report",
                        "--expected-behavior",
                    ],
                    "optional_args": [
                        "--bug-summary",
                        "--steps-to-trigger",
                        "--location-scene",
                        "--location-node",
                        "--location-script",
                        "--frequency-hint",
                        "--severity-hint",
                    ],
                },
            )

    if args.tool == "analyze_bug_report":
        try:
            return 0, build_ok_payload(api.analyze_bug_report(project_root, args))
        except ValueError as exc:
            return 2, build_error_payload(
                ERR_BUG_REPORT_INCOMPLETE,
                str(exc),
                {
                    "required_args": [
                        "--bug-report",
                        "--expected-behavior",
                    ],
                    "optional_args": [
                        "--bug-summary",
                        "--steps-to-trigger",
                        "--location-scene",
                        "--location-node",
                        "--location-script",
                        "--frequency-hint",
                        "--severity-hint",
                    ],
                },
            )

    if args.tool == "define_bug_assertions":
        try:
            return 0, build_ok_payload(api.define_bug_assertions(project_root, args))
        except ValueError as exc:
            return 2, build_error_payload(
                ERR_BUG_REPORT_INCOMPLETE,
                str(exc),
                {
                    "required_args": [
                        "--bug-report",
                        "--expected-behavior",
                    ],
                    "optional_args": [
                        "--bug-summary",
                        "--steps-to-trigger",
                        "--location-scene",
                        "--location-node",
                        "--location-script",
                        "--frequency-hint",
                        "--severity-hint",
                    ],
                },
            )

    if args.tool == "plan_bug_repro_flow":
        try:
            return 0, build_ok_payload(api.plan_bug_repro_flow(project_root, args))
        except ValueError as exc:
            return 2, build_error_payload(
                ERR_BUG_REPORT_INCOMPLETE,
                str(exc),
                {
                    "required_args": [
                        "--bug-report",
                        "--expected-behavior",
                    ],
                    "optional_args": [
                        "--bug-summary",
                        "--steps-to-trigger",
                        "--location-scene",
                        "--location-node",
                        "--location-script",
                        "--frequency-hint",
                        "--severity-hint",
                    ],
                },
            )

    if args.tool == "run_bug_repro_flow":
        try:
            return 0, build_ok_payload(
                api.run_bug_repro_flow(
                    project_root,
                    args,
                    api.normalize_execution_mode(getattr(args, "execution_mode", "play_mode")),
                )
            )
        except ValueError as exc:
            return 2, build_error_payload(
                ERR_BUG_REPORT_INCOMPLETE,
                str(exc),
                {
                    "required_args": [
                        "--bug-report",
                        "--expected-behavior",
                    ],
                    "optional_args": [
                        "--bug-summary",
                        "--steps-to-trigger",
                        "--location-scene",
                        "--location-node",
                        "--location-script",
                        "--frequency-hint",
                        "--severity-hint",
                    ],
                },
            )

    if args.tool == "rerun_bug_repro_flow":
        return 0, build_ok_payload(
            api.rerun_bug_repro_flow(
                project_root,
                args,
                api.normalize_execution_mode(getattr(args, "execution_mode", "play_mode")),
            )
        )

    if args.tool == "plan_bug_fix":
        try:
            return 0, build_ok_payload(api.plan_bug_fix(project_root, args))
        except ValueError as exc:
            return 2, build_error_payload(
                ERR_BUG_REPORT_INCOMPLETE,
                str(exc),
                {
                    "required_args": [
                        "--bug-report",
                        "--expected-behavior",
                    ],
                    "optional_args": [
                        "--bug-summary",
                        "--steps-to-trigger",
                        "--location-scene",
                        "--location-node",
                        "--location-script",
                        "--frequency-hint",
                        "--severity-hint",
                    ],
                },
            )

    if args.tool == "apply_bug_fix":
        try:
            return 0, build_ok_payload(api.apply_bug_fix(project_root, args))
        except ValueError as exc:
            return 2, build_error_payload(
                ERR_BUG_REPORT_INCOMPLETE,
                str(exc),
                {
                    "required_args": [
                        "--bug-report",
                        "--expected-behavior",
                    ],
                    "optional_args": [
                        "--bug-summary",
                        "--steps-to-trigger",
                        "--location-scene",
                        "--location-node",
                        "--location-script",
                        "--frequency-hint",
                        "--severity-hint",
                    ],
                },
            )

    if args.tool == "run_bug_fix_regression":
        return 0, build_ok_payload(api.run_bug_fix_regression(project_root))

    if args.tool == "verify_bug_fix":
        try:
            return 0, build_ok_payload(api.verify_bug_fix(project_root, args))
        except ValueError as exc:
            return 2, build_error_payload(
                ERR_BUG_REPORT_INCOMPLETE,
                str(exc),
                {
                    "required_args": [
                        "--bug-report",
                        "--expected-behavior",
                    ],
                    "optional_args": [
                        "--bug-summary",
                        "--steps-to-trigger",
                        "--location-scene",
                        "--location-node",
                        "--location-script",
                        "--frequency-hint",
                        "--severity-hint",
                    ],
                },
            )

    if args.tool == "configure_godot_executable":
        if not args.godot_executable:
            raise ValueError("--godot-executable is required")
        target = api.configure_godot_executable(project_root, args.godot_executable)
        return 0, build_ok_payload({"status": "configured", "config_file": str(target)})

    if args.tool == "sync_godot_plugin":
        dst = api.sync_project_plugin(project_root)
        return 0, build_ok_payload({"status": "synced", "destination": str(dst)})

    if args.tool == "preflight_project":
        result = api.run_preflight(project_root)
        return (0 if result.ok else 2), build_ok_payload(result.to_dict())

    if args.tool == "run_basic_flow":
        requested_flow_file, early_response, basicflow_context = api.resolve_requested_flow_file(
            project_root,
            args.flow_file,
            bool(getattr(args, "allow_stale_basicflow", False)),
        )
        if early_response is not None:
            return 2, early_response
        if requested_flow_file is None:
            raise ValueError("run_basic_flow could not resolve a flow file")
        return api.run_basic_flow_tool(
            project_root,
            requested_flow_file,
            basicflow_context,
            api.normalize_execution_mode(getattr(args, "execution_mode", "play_mode")),
        )[:2]

    if args.tool == "generate_basic_flow":
        inline_answers = api.collect_inline_generation_answers(args)
        if args.answers_file:
            result = api.generate_basicflow_from_answers_file(project_root, Path(args.answers_file))
        elif inline_answers is not None:
            result = api.generate_basicflow_from_answers(project_root, inline_answers)
        else:
            return 2, build_error_payload(
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
        return 0, build_ok_payload(
            {
                "status": "generated",
                "flow_file": result["paths"]["flow_file"],
                "meta_file": result["paths"]["meta_file"],
                "generation_summary": result["meta"]["generation_summary"],
                "step_count": len(result["flow"]["steps"]),
            }
        )

    if args.tool == "get_basic_flow_generation_questions":
        return 0, build_ok_payload(api.get_basicflow_generation_questions(project_root))

    if args.tool == "get_basic_flow_user_intents":
        return 0, build_ok_payload(api.get_basicflow_user_intents(project_root))

    if args.tool == "get_user_request_command_guide":
        return 0, build_ok_payload(api.get_user_request_command_guide(project_root))

    if args.tool == "resolve_basic_flow_user_request":
        if not args.user_request:
            raise ValueError("--user-request is required")
        return 0, build_ok_payload(api.resolve_basicflow_user_request(project_root, str(args.user_request)))

    if args.tool == "plan_basic_flow_user_request":
        if not args.user_request:
            raise ValueError("--user-request is required")
        return 0, build_ok_payload(api.plan_basicflow_user_request(project_root, str(args.user_request)))

    if args.tool == "plan_user_request":
        if not args.user_request:
            raise ValueError("--user-request is required")
        return 0, build_ok_payload(api.plan_user_request(project_root, str(args.user_request)))

    if args.tool == "handle_user_request":
        if not args.user_request:
            raise ValueError("--user-request is required")
        handled = api.handle_user_request(project_root, str(args.user_request))
        payload = build_ok_payload(handled)
        result = handled.get("result")
        if isinstance(result, dict) and "ok" in result:
            return (0 if bool(result.get("ok", False)) else 2), payload
        return 0, payload

    if args.tool == "start_basic_flow_generation_session":
        return 0, build_ok_payload(api.start_basicflow_generation_session(project_root))

    if args.tool == "answer_basic_flow_generation_session":
        if not args.session_id or not args.question_id or args.answer is None:
            raise ValueError("--session-id, --question-id, and --answer are required")
        return 0, build_ok_payload(
            api.answer_basicflow_generation_session(
                project_root,
                str(args.session_id),
                str(args.question_id),
                str(args.answer),
            )
        )

    if args.tool == "complete_basic_flow_generation_session":
        if not args.session_id:
            raise ValueError("--session-id is required")
        return 0, build_ok_payload(api.complete_basicflow_generation_session(project_root, str(args.session_id)))

    if args.tool == "analyze_basic_flow_staleness":
        return 0, build_ok_payload(api.analyze_basicflow_staleness(project_root))

    return 1, build_error_payload(ERR_UNKNOWN_TOOL, f"unsupported tool: {args.tool}")
