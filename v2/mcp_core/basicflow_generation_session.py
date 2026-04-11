from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .basicflow_generation import BasicFlowGenerationError, generate_basicflow_from_answers, get_basicflow_generation_questions


class BasicFlowGenerationSessionError(ValueError):
    pass


def _session_path(project_root: Path) -> Path:
    return (project_root.resolve() / "pointer_gpf" / "tmp" / "basicflow_generation_session.json").resolve()


def start_basicflow_generation_session(project_root: Path) -> dict[str, Any]:
    questions = get_basicflow_generation_questions(project_root)
    payload = {
        "schema": "pointer_gpf.v2.basicflow_generation_session.v1",
        "session_id": uuid.uuid4().hex,
        "status": "awaiting_answer",
        "answers": {},
        "questions": questions["questions"],
    }
    _write_session(project_root, payload)
    return _session_view(payload)


def answer_basicflow_generation_session(
    project_root: Path,
    *,
    session_id: str,
    question_id: str,
    answer: str,
) -> dict[str, Any]:
    payload = _read_session(project_root)
    if payload.get("session_id") != session_id:
        raise BasicFlowGenerationSessionError("basicflow generation session id does not match the active session")
    answers = dict(payload.get("answers", {}))
    normalized_id = str(question_id).strip()
    if normalized_id not in {"main_scene_is_entry", "entry_scene_path", "tested_features", "include_screenshot_evidence"}:
        raise BasicFlowGenerationSessionError(f"unsupported basicflow generation question id: {question_id!r}")

    if normalized_id in {"main_scene_is_entry", "include_screenshot_evidence"}:
        answers[normalized_id] = _parse_bool_answer(answer)
    elif normalized_id == "tested_features":
        answers[normalized_id] = answer
    else:
        answers[normalized_id] = answer.strip()

    payload["answers"] = answers
    payload["status"] = "ready_to_generate" if _next_question(payload) is None else "awaiting_answer"
    _write_session(project_root, payload)
    return _session_view(payload)


def complete_basicflow_generation_session(project_root: Path, *, session_id: str) -> dict[str, Any]:
    payload = _read_session(project_root)
    if payload.get("session_id") != session_id:
        raise BasicFlowGenerationSessionError("basicflow generation session id does not match the active session")
    next_question = _next_question(payload)
    if next_question is not None:
        raise BasicFlowGenerationSessionError(
            f"basicflow generation session is incomplete; next required question is {next_question['id']!r}"
        )
    try:
        generated = generate_basicflow_from_answers(project_root, dict(payload.get("answers", {})))
    except BasicFlowGenerationError as exc:
        raise BasicFlowGenerationSessionError(str(exc)) from exc
    session_path = _session_path(project_root)
    session_path.unlink(missing_ok=True)
    return {
        "status": "generated",
        "session_id": session_id,
        "flow_file": generated["paths"]["flow_file"],
        "meta_file": generated["paths"]["meta_file"],
        "generation_summary": generated["meta"]["generation_summary"],
        "step_count": len(generated["flow"]["steps"]),
    }


def _session_view(payload: dict[str, Any]) -> dict[str, Any]:
    next_question = _next_question(payload)
    return {
        "status": str(payload.get("status", "awaiting_answer")),
        "session_id": str(payload.get("session_id", "")),
        "answers": dict(payload.get("answers", {})),
        "next_question": next_question,
        "remaining_question_ids": [item["id"] for item in _remaining_questions(payload)],
    }


def _remaining_questions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    answers = dict(payload.get("answers", {}))
    questions = list(payload.get("questions", []))
    out: list[dict[str, Any]] = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("id", "")).strip()
        if question_id == "main_scene_is_entry":
            if question_id not in answers:
                out.append(item)
            elif answers.get("main_scene_is_entry") is False and "entry_scene_path" not in answers:
                out.append(
                    {
                        "id": "entry_scene_path",
                        "question": "如主场景不是游戏主流程入口，请补充真正入口场景路径。",
                        "type": "string",
                        "required": True,
                    }
                )
            continue
        if question_id not in answers:
            out.append(item)
    return out


def _next_question(payload: dict[str, Any]) -> dict[str, Any] | None:
    remaining = _remaining_questions(payload)
    return remaining[0] if remaining else None


def _read_session(project_root: Path) -> dict[str, Any]:
    path = _session_path(project_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BasicFlowGenerationSessionError("no active basicflow generation session exists for this project") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BasicFlowGenerationSessionError("could not read the active basicflow generation session") from exc
    if not isinstance(payload, dict):
        raise BasicFlowGenerationSessionError("active basicflow generation session is invalid")
    return payload


def _write_session(project_root: Path, payload: dict[str, Any]) -> None:
    path = _session_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _parse_bool_answer(raw: str) -> bool:
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "y", "是"}:
        return True
    if value in {"0", "false", "no", "n", "否"}:
        return False
    raise BasicFlowGenerationSessionError(f"invalid boolean answer: {raw!r}")
