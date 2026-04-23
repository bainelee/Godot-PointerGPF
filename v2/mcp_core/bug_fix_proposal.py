from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ALLOWED_PROPOSAL_EDIT_KINDS = {"replace_text", "insert_after", "insert_before"}
ALLOWED_PROPOSAL_SUFFIXES = {".gd", ".tscn"}


def proposal_path(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp" / "last_bug_fix_proposal.json").resolve()


def application_path(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp" / "last_bug_fix_application.json").resolve()


def _raw_proposal_args(args: Any) -> tuple[str, str]:
    return (
        str(getattr(args, "fix_proposal_json", "") or "").strip(),
        str(getattr(args, "fix_proposal_file", "") or "").strip(),
    )


def _load_proposal_json(raw_json: str) -> tuple[dict[str, Any] | None, str]:
    if not raw_json:
        return None, ""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return None, f"fix proposal JSON is not valid: {exc}"
    return payload if isinstance(payload, dict) else None, "" if isinstance(payload, dict) else "fix proposal JSON root must be an object"


def _load_proposal_file(project_root: Path, file_text: str) -> tuple[dict[str, Any] | None, str]:
    if not file_text:
        return None, ""
    path = Path(file_text)
    if not path.is_absolute():
        path = (project_root / path).resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return None, f"could not read fix proposal file: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"fix proposal file is not valid JSON: {exc}"
    return payload if isinstance(payload, dict) else None, "" if isinstance(payload, dict) else "fix proposal file root must be an object"


def load_fix_proposal(project_root: Path, args: Any) -> dict[str, Any]:
    raw_json, raw_file = _raw_proposal_args(args)
    if not raw_json and not raw_file:
        return {
            "status": "not_provided",
            "proposal": {},
            "rejected_reasons": [],
            "source": "",
        }
    source = "json" if raw_json else "file"
    proposal, error = _load_proposal_json(raw_json) if raw_json else _load_proposal_file(project_root, raw_file)
    if proposal is None:
        return {
            "status": "rejected",
            "proposal": {},
            "rejected_reasons": [error or "fix proposal could not be loaded"],
            "source": source,
        }
    return {
        "status": "loaded",
        "proposal": proposal,
        "rejected_reasons": [],
        "source": source,
    }


def _candidate_path_map(project_root: Path, fix_plan: dict[str, Any]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    candidates = fix_plan.get("candidate_files", [])
    if not isinstance(candidates, list):
        return out
    for item in candidates:
        if not isinstance(item, dict):
            continue
        path_text = str(item.get("path", "")).strip()
        if not path_text:
            continue
        if path_text.startswith("res://"):
            absolute = (project_root / path_text.replace("res://", "").replace("/", "\\")).resolve()
        else:
            absolute_text = str(item.get("absolute_path", "")).strip()
            absolute = Path(absolute_text).resolve() if absolute_text else Path()
        if str(absolute):
            out[path_text] = absolute
    return out


def _validate_edit(edit: dict[str, Any], index: int) -> list[str]:
    reasons: list[str] = []
    kind = str(edit.get("kind", "")).strip()
    if kind not in ALLOWED_PROPOSAL_EDIT_KINDS:
        reasons.append(f"edit {index} uses unsupported kind: {kind}")
    find_text = str(edit.get("find", ""))
    if not find_text:
        reasons.append(f"edit {index} requires non-empty find")
    if kind == "replace_text" and "replace" not in edit:
        reasons.append(f"edit {index} replace_text requires replace")
    if kind in {"insert_after", "insert_before"} and "text" not in edit:
        reasons.append(f"edit {index} {kind} requires text")
    return reasons


def validate_fix_proposal(project_root: Path, fix_plan: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    candidate_file = str(proposal.get("candidate_file", "")).strip()
    if not candidate_file:
        reasons.append("candidate_file is required")
    if Path(candidate_file).suffix not in ALLOWED_PROPOSAL_SUFFIXES:
        reasons.append("candidate_file must be a .gd or .tscn file")
    candidates = _candidate_path_map(project_root, fix_plan)
    if candidate_file and candidate_file not in candidates:
        reasons.append("candidate_file is not present in plan_bug_fix.candidate_files")
    edits = proposal.get("edits", [])
    if not isinstance(edits, list) or not edits:
        reasons.append("edits must be a non-empty list")
    elif len(edits) > 5:
        reasons.append("edits must contain at most 5 items")
    else:
        for index, edit in enumerate(edits):
            if not isinstance(edit, dict):
                reasons.append(f"edit {index} must be an object")
                continue
            reasons.extend(_validate_edit(edit, index))
    target_path = candidates.get(candidate_file, Path())
    if target_path and not target_path.is_file():
        reasons.append(f"candidate_file does not exist on disk: {candidate_file}")
    return {
        "status": "accepted" if not reasons else "rejected",
        "proposal": deepcopy(proposal) if not reasons else {},
        "rejected_reasons": reasons,
        "target_path": str(target_path) if target_path else "",
    }


def _apply_one_edit(text: str, edit: dict[str, Any], index: int) -> tuple[str, dict[str, Any]]:
    kind = str(edit.get("kind", "")).strip()
    find_text = str(edit.get("find", ""))
    match_count = text.count(find_text)
    if match_count != 1:
        return text, {
            "status": "rejected",
            "reason": f"edit {index} find text must appear exactly once; found {match_count}",
            "kind": kind,
        }
    if kind == "replace_text":
        updated = text.replace(find_text, str(edit.get("replace", "")), 1)
    elif kind == "insert_after":
        insert_text = find_text + str(edit.get("text", ""))
        updated = text.replace(find_text, insert_text, 1)
    elif kind == "insert_before":
        insert_text = str(edit.get("text", "")) + find_text
        updated = text.replace(find_text, insert_text, 1)
    else:
        return text, {
            "status": "rejected",
            "reason": f"edit {index} uses unsupported kind: {kind}",
            "kind": kind,
        }
    return updated, {
        "status": "applied",
        "kind": kind,
        "find": find_text,
    }


def write_fix_proposal_artifact(project_root: Path, payload: dict[str, Any]) -> Path:
    target = proposal_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_fix_application_artifact(project_root: Path, payload: dict[str, Any]) -> Path:
    target = application_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def apply_validated_fix_proposal(project_root: Path, fix_plan: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    validation = validate_fix_proposal(project_root, fix_plan, proposal)
    proposal_artifact = write_fix_proposal_artifact(
        project_root,
        {
            "schema": "pointer_gpf.v2.fix_proposal.v1",
            "project_root": str(project_root.resolve()),
            "status": validation["status"],
            "proposal": proposal if validation["status"] == "accepted" else {},
            "rejected_reasons": validation["rejected_reasons"],
        },
    )
    if validation["status"] != "accepted":
        return {
            "status": "fix_proposal_rejected",
            "message": "; ".join(validation["rejected_reasons"]),
            "applied": False,
            "applied_changes": [],
            "proposal_artifact": str(proposal_artifact),
        }

    target_path = Path(str(validation["target_path"]))
    original = target_path.read_text(encoding="utf-8")
    updated = original
    edit_results: list[dict[str, Any]] = []
    for index, edit in enumerate(proposal.get("edits", [])):
        updated, result = _apply_one_edit(updated, edit, index)
        edit_results.append(result)
        if str(result.get("status", "")).strip() != "applied":
            return {
                "status": "fix_proposal_rejected",
                "message": str(result.get("reason", "")).strip(),
                "applied": False,
                "applied_changes": [],
                "proposal_artifact": str(proposal_artifact),
                "edit_results": edit_results,
            }

    if updated == original:
        return {
            "status": "already_aligned",
            "message": "proposal produced no file changes",
            "applied": False,
            "applied_changes": [],
            "proposal_artifact": str(proposal_artifact),
            "edit_results": edit_results,
        }

    target_path.write_text(updated, encoding="utf-8")
    applied_change = {
        "path": str(proposal.get("candidate_file", "")).strip(),
        "absolute_path": str(target_path),
        "strategy": "bounded_model_fix_proposal",
        "edit_count": len(edit_results),
    }
    application_artifact = write_fix_application_artifact(
        project_root,
        {
            "schema": "pointer_gpf.v2.fix_application.v1",
            "project_root": str(project_root.resolve()),
            "status": "fix_applied",
            "applied_changes": [applied_change],
            "edit_results": edit_results,
        },
    )
    return {
        "status": "fix_applied",
        "message": "applied bounded model fix proposal",
        "applied": True,
        "applied_changes": [applied_change],
        "proposal_artifact": str(proposal_artifact),
        "application_artifact": str(application_artifact),
        "edit_results": edit_results,
    }
