from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import ALLOWED_FLOW_ACTIONS


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FlowContractError(ValueError):
    pass


class FlowExecutionTimeout(Exception):
    def __init__(self, message: str, *, step_index: int, step_id: str, run_id: str) -> None:
        super().__init__(message)
        self.step_index = step_index
        self.step_id = step_id
        self.run_id = run_id


class FlowExecutionStepFailed(Exception):
    def __init__(self, message: str, *, step_index: int, step_id: str, run_id: str) -> None:
        super().__init__(message)
        self.step_index = step_index
        self.step_id = step_id
        self.run_id = run_id


class FlowExecutionEngineStalled(Exception):
    def __init__(self, message: str, *, diagnostics: dict[str, Any], run_id: str) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics
        self.run_id = run_id
        self.step_index = -1
        self.step_id = ""


@dataclass(slots=True)
class FlowRunOptions:
    project_root: Path
    flow_file: Path
    report_dir: Path
    step_timeout_ms: int = 30_000
    fail_fast: bool = True


def load_flow(flow_file: Path) -> dict[str, Any]:
    # Accept UTF-8 JSON files with or without BOM so flows written from PowerShell
    # can still be loaded by the V2 runner.
    data = json.loads(flow_file.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise FlowContractError("flow payload must be an object")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise FlowContractError("flow.steps must be a non-empty list")
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise FlowContractError(f"flow step #{idx} must be an object")
        action = str(step.get("action", "")).strip()
        if action not in ALLOWED_FLOW_ACTIONS:
            raise FlowContractError(f"unsupported flow action at step #{idx}: {action!r}")
    return data


class FlowRunner:
    def __init__(self, options: FlowRunOptions) -> None:
        self.options = options
        self.run_id = uuid.uuid4().hex
        self.runtime_evidence_records: list[dict[str, Any]] = []
        self.runtime_evidence_refs: list[str] = []
        self._runtime_evidence_record_ids: set[str] = set()

    def bridge_dir(self) -> Path:
        return (self.options.project_root / "pointer_gpf" / "tmp").resolve()

    def command_path(self) -> Path:
        return self.bridge_dir() / "command.json"

    def response_path(self) -> Path:
        return self.bridge_dir() / "response.json"

    def diagnostics_path(self) -> Path:
        return self.bridge_dir() / "runtime_diagnostics.json"

    def events_path(self) -> Path:
        return self.options.report_dir / f"flow_run_events_{self.run_id}.ndjson"

    def report_path(self) -> Path:
        return self.options.report_dir / f"flow_run_report_{self.run_id}.json"

    def _append_event(self, payload: dict[str, Any]) -> None:
        self.options.report_dir.mkdir(parents=True, exist_ok=True)
        with self.events_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _record_runtime_evidence_from_response(self, response: dict[str, Any]) -> None:
        raw_records = response.get("runtime_evidence_records", [])
        if isinstance(raw_records, list):
            for item in raw_records:
                if not isinstance(item, dict):
                    continue
                evidence_id = str(item.get("evidence_id", "") or item.get("id", "")).strip()
                if evidence_id and evidence_id in self._runtime_evidence_record_ids:
                    continue
                if evidence_id:
                    self._runtime_evidence_record_ids.add(evidence_id)
                self.runtime_evidence_records.append(item)
                if evidence_id and evidence_id not in self.runtime_evidence_refs:
                    self.runtime_evidence_refs.append(evidence_id)
        raw_refs = response.get("runtime_evidence_refs", [])
        if isinstance(raw_refs, list):
            for item in raw_refs:
                evidence_id = str(item).strip()
                if evidence_id and evidence_id not in self.runtime_evidence_refs:
                    self.runtime_evidence_refs.append(evidence_id)

    def _runtime_evidence_summary(self) -> dict[str, Any]:
        failed: list[str] = []
        inconclusive: list[str] = []
        for record in self.runtime_evidence_records:
            evidence_id = str(record.get("evidence_id", "") or record.get("id", "")).strip()
            status = str(record.get("status", "")).strip().lower()
            if evidence_id and status == "failed":
                failed.append(evidence_id)
            elif evidence_id and status == "inconclusive":
                inconclusive.append(evidence_id)
        return {
            "record_count": len(self.runtime_evidence_records),
            "failed_evidence_ids": failed,
            "inconclusive_evidence_ids": inconclusive,
            "evidence_by_check_id": {},
        }

    def _read_blocking_diagnostics(self) -> dict[str, Any] | None:
        path = self.diagnostics_path()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        if str(data.get("severity", "")).strip().lower() not in {"error", "fatal"}:
            return None
        items = data.get("items")
        if not isinstance(items, list):
            return None
        blocking = []
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "")).strip().lower()
            msg = str(item.get("message", "")).strip().lower()
            if kind == "engine_log_error":
                blocking.append(item)
            elif kind == "bridge_error" and "acknowledged" not in msg:
                blocking.append(item)
        if not blocking:
            return None
        out = dict(data)
        out["blocking_items"] = blocking
        return out

    def _wait_for_response(self, seq: int, deadline: float) -> dict[str, Any]:
        rsp = self.response_path()
        while time.monotonic() < deadline:
            blocking = self._read_blocking_diagnostics()
            if blocking is not None:
                raise FlowExecutionEngineStalled(
                    "runtime diagnostics reported error/fatal while waiting for bridge response",
                    diagnostics=blocking,
                    run_id=self.run_id,
                )
            if rsp.is_file():
                try:
                    payload = json.loads(rsp.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    time.sleep(0.02)
                    continue
                if not isinstance(payload, dict):
                    time.sleep(0.02)
                    continue
                if int(payload.get("seq", -1)) == seq and str(payload.get("run_id", "")) == self.run_id:
                    return payload
            time.sleep(0.02)
        raise FlowExecutionTimeout(
            f"bridge did not respond within step_timeout_ms (seq={seq})",
            step_index=-1,
            step_id="",
            run_id=self.run_id,
        )

    def _run_step(self, step_index: int, step: dict[str, Any]) -> dict[str, Any]:
        step_id = str(step.get("id", f"step_{step_index}")).strip() or f"step_{step_index}"
        self._append_event({"phase": "started", "run_id": self.run_id, "step_index": step_index, "step_id": step_id, "ts": _utc_iso()})
        seq = step_index + 1
        self.bridge_dir().mkdir(parents=True, exist_ok=True)
        if self.response_path().exists():
            self.response_path().unlink()
        command = {
            "schema": "pointer_gpf.v2.flow_command.v1",
            "run_id": self.run_id,
            "seq": seq,
            "step_index": step_index,
            "step_id": step_id,
            "step": step,
        }
        self.command_path().write_text(json.dumps(command, ensure_ascii=False), encoding="utf-8")
        deadline = time.monotonic() + max(1, int(self.options.step_timeout_ms)) / 1000.0
        try:
            response = self._wait_for_response(seq, deadline)
        except FlowExecutionTimeout as exc:
            exc.step_index = step_index
            exc.step_id = step_id
            raise
        except FlowExecutionEngineStalled as exc:
            exc.step_index = step_index
            exc.step_id = step_id
            raise
        ok = bool(response.get("ok", False))
        self._record_runtime_evidence_from_response(response)
        self._append_event(
            {
                "phase": "result",
                "run_id": self.run_id,
                "step_index": step_index,
                "step_id": step_id,
                "ts": _utc_iso(),
                "bridge_ok": ok,
                "bridge_message": str(response.get("message", "")),
                "bridge_details": response.get("details", {}) if isinstance(response.get("details", {}), dict) else {},
                "runtime_evidence_refs": response.get("runtime_evidence_refs", [])
                if isinstance(response.get("runtime_evidence_refs", []), list)
                else [],
            }
        )
        self._append_event(
            {
                "phase": "verify",
                "run_id": self.run_id,
                "step_index": step_index,
                "step_id": step_id,
                "ts": _utc_iso(),
                "verified": ok,
            }
        )
        if self.options.fail_fast and not ok:
            detail_keys = ("message", "hint", "reason", "elapsedMs", "conditionMet")
            details = [f"{k}={response.get(k)!r}" for k in detail_keys if k in response]
            raise FlowExecutionStepFailed(
                f"bridge reported failure for step {step_id!r}" + (f" ({', '.join(details)})" if details else ""),
                step_index=step_index,
                step_id=step_id,
                run_id=self.run_id,
            )
        return response

    def run(self, flow_payload: dict[str, Any]) -> dict[str, Any]:
        self.options.report_dir.mkdir(parents=True, exist_ok=True)
        if self.events_path().exists():
            self.events_path().unlink()
        self.runtime_evidence_records = []
        self.runtime_evidence_refs = []
        self._runtime_evidence_record_ids = set()
        # Each run must start from a clean bridge state; otherwise a stale
        # diagnostics file from a previous failed run can incorrectly fail the
        # new run before its first step has actually executed.
        self.command_path().unlink(missing_ok=True)
        self.response_path().unlink(missing_ok=True)
        self.diagnostics_path().unlink(missing_ok=True)
        status = "passed"
        steps = [step for step in flow_payload.get("steps", []) if isinstance(step, dict)]
        try:
            for idx, step in enumerate(steps):
                self._run_step(idx, step)
        except FlowExecutionStepFailed:
            status = "failed"
            raise
        except FlowExecutionTimeout:
            status = "timeout"
            raise
        except FlowExecutionEngineStalled:
            status = "engine_stalled"
            raise
        finally:
            report = {
                "run_id": self.run_id,
                "status": status,
                "step_count": len(steps),
                "events_file": str(self.events_path()),
                "report_file": str(self.report_path()),
                "flow_file": str(self.options.flow_file.resolve()),
                "flow_id": str(flow_payload.get("flowId", "")),
                "runtime_evidence_records": self.runtime_evidence_records,
                "runtime_evidence_refs": self.runtime_evidence_refs,
                "runtime_evidence_summary": self._runtime_evidence_summary(),
            }
            self.report_path().write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report


def run_basic_flow(project_root: Path, flow_file: Path, *, step_timeout_ms: int = 30_000) -> dict[str, Any]:
    flow = load_flow(flow_file)
    runner = FlowRunner(
        FlowRunOptions(
            project_root=project_root.resolve(),
            flow_file=flow_file.resolve(),
            report_dir=(project_root / "pointer_gpf" / "gpf-exp" / "runtime").resolve(),
            step_timeout_ms=step_timeout_ms,
        )
    )
    return runner.run(flow)
