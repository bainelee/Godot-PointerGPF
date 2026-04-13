from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

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


def normalize_user_request(text: str) -> str:
    normalized = str(text).strip().lower()
    for token in ('"', "'", "“", "”", "‘", "’", "，", ",", "。", ".", "！", "!", "？", "?", "：", ":", "；", ";"):
        normalized = normalized.replace(token, " ")
    return " ".join(part for part in normalized.split() if part)


def extract_windows_executable_path(text: str) -> str:
    match = _WINDOWS_EXE_PATH_RE.search(str(text))
    if not match:
        return ""
    return str(match.group(1)).strip()


def matches_user_phrase(request_text: str, phrases: list[str]) -> bool:
    normalized_request = normalize_user_request(request_text)
    if normalized_request == "":
        return False
    for phrase in phrases:
        normalized_phrase = normalize_user_request(phrase)
        if normalized_phrase and normalized_phrase in normalized_request:
            return True
    return False


def basicflow_user_intent_payload(
    project_root: Path,
    *,
    detect_basicflow_staleness: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
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


def project_readiness_request_catalog(project_root: Path) -> dict[str, Any]:
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


def user_request_command_guide(
    project_root: Path,
    *,
    detect_basicflow_staleness: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    basicflow_catalog = basicflow_user_intent_payload(
        project_root,
        detect_basicflow_staleness=detect_basicflow_staleness,
    )
    readiness_catalog = project_readiness_request_catalog(project_root)
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


def resolve_project_readiness_user_request(project_root: Path, user_request: str) -> dict[str, Any]:
    catalog = project_readiness_request_catalog(project_root)
    for intent in catalog["intents"]:
        phrases = intent.get("user_phrases", [])
        if isinstance(phrases, list) and matches_user_phrase(user_request, [str(item) for item in phrases]):
            tool = str(intent.get("tool", "")).strip()
            project_root_str = str(project_root.resolve())
            if tool == "configure_godot_executable":
                executable = extract_windows_executable_path(user_request)
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


def resolve_basicflow_user_request(
    project_root: Path,
    user_request: str,
    *,
    detect_basicflow_staleness: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    intent_payload = basicflow_user_intent_payload(
        project_root,
        detect_basicflow_staleness=detect_basicflow_staleness,
    )
    matched_intent: dict[str, Any] | None = None
    for intent in intent_payload["intents"]:
        phrases = intent.get("user_phrases", [])
        if isinstance(phrases, list) and matches_user_phrase(user_request, [str(item) for item in phrases]):
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


def plan_basicflow_user_request(
    project_root: Path,
    user_request: str,
    *,
    detect_basicflow_staleness: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    resolution = resolve_basicflow_user_request(
        project_root,
        user_request,
        detect_basicflow_staleness=detect_basicflow_staleness,
    )
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


def plan_user_request(
    project_root: Path,
    user_request: str,
    *,
    detect_basicflow_staleness: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    basicflow_plan = plan_basicflow_user_request(
        project_root,
        user_request,
        detect_basicflow_staleness=detect_basicflow_staleness,
    )
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
    readiness_resolution = resolve_project_readiness_user_request(project_root, user_request)
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


def handle_user_request(
    project_root: Path,
    user_request: str,
    *,
    detect_basicflow_staleness: Callable[[Path], dict[str, Any]],
    run_preflight: Callable[[Path], Any],
    configure_godot_executable: Callable[[Path, str], Path],
    get_basicflow_generation_questions: Callable[[Path], dict[str, Any]],
    analyze_basicflow_staleness: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    plan = plan_user_request(
        project_root,
        user_request,
        detect_basicflow_staleness=detect_basicflow_staleness,
    )
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
