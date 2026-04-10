"""Map runtime / flow failures to stable remediation_class strings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FailureSignal:
    app_error_code: str | None
    step_status: str | None
    diagnostics_severity: str | None


def classify_failure(signal: FailureSignal) -> str:
    code = (signal.app_error_code or "").strip().upper()
    step = (signal.step_status or "").strip().lower()

    if code == "RUNTIME_GATE_FAILED":
        return "runtime_gate"
    if code == "ENGINE_RUNTIME_STALLED":
        return "engine_runtime_error"
    if code == "TIMEOUT":
        return "bridge_timeout"
    if code == "STEP_FAILED":
        return "flow_step_failed"
    if code == "FLOW_GENERATION_BLOCKED":
        return "flow_generation_blocked"
    if code == "PROJECT_GODOT_NOT_FOUND":
        return "invalid_godot_project"
    if step in ("failed", "error", "timeout") and not code:
        return "flow_step_failed"
    if code:
        return "unknown_failure"
    return "unknown_failure"
