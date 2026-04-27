from __future__ import annotations

from typing import Any


def _stage_artifact(artifact_summary: dict[str, Any], key: str) -> str:
    by_stage = artifact_summary.get("by_stage", {})
    if not isinstance(by_stage, dict):
        return ""
    return str(by_stage.get(key, "")).strip()


def _compact_paths(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    paths: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "") or item.get("absolute_path", "")).strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _line(label: str, value: str, artifact: str = "") -> str:
    if artifact:
        return f"- {label}: {value} (artifact: {artifact})"
    return f"- {label}: {value}"


def format_repair_report(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("repair_summary", {})
    if not isinstance(summary, dict):
        summary = {}
    artifact_summary = payload.get("artifact_summary", summary.get("artifact_summary", {}))
    if not isinstance(artifact_summary, dict):
        artifact_summary = {"files": [], "by_stage": {}}

    repro = summary.get("repro", {})
    fix_plan = summary.get("fix_plan", {})
    apply = summary.get("apply", {})
    rerun = summary.get("rerun", {})
    regression = summary.get("regression", {})
    if not isinstance(repro, dict):
        repro = {}
    if not isinstance(fix_plan, dict):
        fix_plan = {}
    if not isinstance(apply, dict):
        apply = {}
    if not isinstance(rerun, dict):
        rerun = {}
    if not isinstance(regression, dict):
        regression = {}

    changed_files = _compact_paths(apply.get("applied_changes", []))
    evidence_ids = []
    for value in repro.get("runtime_evidence_ids", []), rerun.get("runtime_evidence_ids", []):
        if isinstance(value, list):
            for item in value:
                text = str(item).strip()
                if text and text not in evidence_ids:
                    evidence_ids.append(text)

    final_status = str(summary.get("status", payload.get("status", ""))).strip()
    bug_summary = str(summary.get("bug_summary", payload.get("bug_summary", ""))).strip()
    bug_source = str(summary.get("bug_source", "")).strip() or "unknown"
    source_text = bug_source
    injected_kind = str(summary.get("injected_bug_kind", "")).strip()
    if injected_kind:
        source_text = f"{bug_source} ({injected_kind})"

    sections = {
        "bug": {
            "summary": bug_summary,
            "source": source_text,
            "round_id": str(summary.get("round_id", "")).strip(),
            "bug_id": str(summary.get("bug_id", "")).strip(),
        },
        "repro": {
            "status": str(repro.get("status", "")).strip(),
            "failed_phase": str(repro.get("failed_phase", "")).strip(),
            "failed_check_ids": repro.get("failed_check_ids", []) if isinstance(repro.get("failed_check_ids", []), list) else [],
            "runtime_evidence_ids": repro.get("runtime_evidence_ids", []) if isinstance(repro.get("runtime_evidence_ids", []), list) else [],
            "artifact": _stage_artifact(artifact_summary, "repro_artifact") or str(repro.get("artifact_file", "")).strip(),
        },
        "fix": {
            "plan_status": str(fix_plan.get("status", "")).strip(),
            "candidate_files": _compact_paths(fix_plan.get("candidate_files", [])),
            "fix_goals": fix_plan.get("fix_goals", []) if isinstance(fix_plan.get("fix_goals", []), list) else [],
            "apply_status": str(apply.get("status", "")).strip(),
            "changed_files": changed_files,
            "proposal_artifact": _stage_artifact(artifact_summary, "proposal_artifact") or str(apply.get("proposal_artifact", "")).strip(),
            "application_artifact": _stage_artifact(artifact_summary, "application_artifact") or str(apply.get("application_artifact", "")).strip(),
        },
        "verification": {
            "rerun_status": str(rerun.get("status", "")).strip(),
            "rerun_evidence_ids": rerun.get("runtime_evidence_ids", []) if isinstance(rerun.get("runtime_evidence_ids", []), list) else [],
            "rerun_artifact": _stage_artifact(artifact_summary, "rerun_artifact") or str(rerun.get("artifact_file", "")).strip(),
            "regression_status": str(regression.get("status", "")).strip(),
            "regression_artifact": _stage_artifact(artifact_summary, "regression_artifact") or str(regression.get("artifact_file", "")).strip(),
        },
        "artifacts": artifact_summary,
    }

    lines = [
        f"Repair status: {final_status}",
        _line("Bug", bug_summary),
        _line("Bug source", source_text),
    ]
    if sections["bug"]["round_id"]:
        lines.append(_line("Round id", sections["bug"]["round_id"]))
    if sections["bug"]["bug_id"]:
        lines.append(_line("Bug id", sections["bug"]["bug_id"]))
    lines.extend(
        [
            _line("Repro", sections["repro"]["status"], sections["repro"]["artifact"]),
            _line("Failed checks", ", ".join(sections["repro"]["failed_check_ids"]) or "none", sections["repro"]["artifact"]),
            _line("Runtime evidence", ", ".join(evidence_ids) or "none", sections["repro"]["artifact"]),
            _line("Fix application", sections["fix"]["apply_status"], sections["fix"]["application_artifact"]),
            _line("Changed files", ", ".join(changed_files) or "none", sections["fix"]["application_artifact"]),
            _line("Bug-focused rerun", sections["verification"]["rerun_status"], sections["verification"]["rerun_artifact"]),
            _line("Regression", sections["verification"]["regression_status"], sections["verification"]["regression_artifact"]),
        ]
    )

    return {
        "schema": "pointer_gpf.v2.user_repair_report.v1",
        "status": final_status,
        "summary": f"{bug_summary}: {final_status}" if bug_summary else final_status,
        "sections": sections,
        "markdown": "\n".join(lines),
    }
