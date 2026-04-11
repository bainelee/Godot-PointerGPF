from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ERR_UNKNOWN_TOOL = "UNKNOWN_TOOL"
ERR_PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
ERR_MULTIPLE_EDITOR_PROCESSES_DETECTED = "MULTIPLE_EDITOR_PROCESSES_DETECTED"
ERR_FLOW_ALREADY_RUNNING = "FLOW_ALREADY_RUNNING"
ERR_STEP_FAILED = "STEP_FAILED"
ERR_TIMEOUT = "TIMEOUT"
ERR_ENGINE_RUNTIME_STALLED = "ENGINE_RUNTIME_STALLED"
ERR_TEARDOWN_VERIFICATION_FAILED = "TEARDOWN_VERIFICATION_FAILED"
ERR_BASICFLOW_MISSING = "BASICFLOW_MISSING"
ERR_BASICFLOW_STALE = "BASICFLOW_STALE"
ERR_BASICFLOW_GENERATION_ANSWERS_REQUIRED = "BASICFLOW_GENERATION_ANSWERS_REQUIRED"
ERR_BASICFLOW_GENERATION_SESSION_NOT_FOUND = "BASICFLOW_GENERATION_SESSION_NOT_FOUND"
ERR_BASICFLOW_GENERATION_SESSION_INVALID = "BASICFLOW_GENERATION_SESSION_INVALID"
ERR_BASICFLOW_GENERATION_SESSION_INCOMPLETE = "BASICFLOW_GENERATION_SESSION_INCOMPLETE"


ALLOWED_FLOW_ACTIONS = frozenset(
    {
        "launchGame",
        "click",
        "wait",
        "check",
        "snapshot",
        "closeProject",
    }
)


@dataclass(slots=True)
class PreflightIssue:
    code: str
    message: str
    severity: str = "error"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PreflightResult:
    ok: bool
    project_root: Path
    issues: list[PreflightIssue] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "project_root": str(self.project_root),
            "issues": [item.to_dict() for item in self.issues],
            "checks": self.checks,
        }


def build_ok_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "result": result}


def build_error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return payload
