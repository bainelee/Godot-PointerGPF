"""MCP-side flow runner: file bridge (command.json / response.json) and three-phase event logging."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_]+", "_", str(text).strip())
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw.lower() or "flow_run"


class FlowExecutionTimeout(Exception):
    def __init__(self, message: str, *, step_index: int, step_id: str, run_id: str) -> None:
        super().__init__(message)
        self.step_index = step_index
        self.step_id = step_id
        self.run_id = run_id
        self.report: dict[str, Any] | None = None


class FlowExecutionStepFailed(Exception):
    def __init__(self, message: str, *, step_index: int, step_id: str, run_id: str) -> None:
        super().__init__(message)
        self.step_index = step_index
        self.step_id = step_id
        self.run_id = run_id
        self.report: dict[str, Any] | None = None


@dataclass
class FlowRunOptions:
    project_root: Path
    flow_file: Path
    report_dir: Path
    step_timeout_ms: int = 30_000
    run_id: str | None = None
    fail_fast: bool = True


class FlowRunner:
    """Execute flow steps via pointer_gpf/tmp/command.json ↔ response.json and emit started/result/verify events."""

    def __init__(self, options: FlowRunOptions) -> None:
        self.options = options
        self._run_id = (options.run_id or "").strip() or uuid.uuid4().hex
        self._slug = _slugify(self._run_id)

    def _bridge_dir(self) -> Path:
        return (self.options.project_root / "pointer_gpf" / "tmp").resolve()

    def _command_path(self) -> Path:
        return self._bridge_dir() / "command.json"

    def _response_path(self) -> Path:
        return self._bridge_dir() / "response.json"

    def _append_ndjson(self, path: Path, obj: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def _emit_event(self, events_path: Path, phase: str, step_index: int, step_id: str, extra: dict[str, Any] | None = None) -> None:
        row: dict[str, Any] = {
            "phase": phase,
            "run_id": self._run_id,
            "step_index": step_index,
            "step_id": step_id,
            "ts": _utc_iso(),
        }
        if extra:
            row.update(extra)
        self._append_ndjson(events_path, row)

    def _step_for_bridge(self, step: dict[str, Any]) -> dict[str, Any]:
        out = dict(step)
        out.pop("chat_contract", None)
        return out

    def _wait_for_response(self, seq: int, deadline: float) -> dict[str, Any]:
        rsp = self._response_path()
        while time.monotonic() < deadline:
            if rsp.is_file():
                try:
                    payload = json.loads(rsp.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    time.sleep(0.02)
                    continue
                if isinstance(payload, dict) and int(payload.get("seq", -1)) == seq and str(payload.get("run_id", "")) == self._run_id:
                    return payload
            time.sleep(0.02)
        raise FlowExecutionTimeout(
            f"bridge did not respond within step_timeout_ms (seq={seq})",
            step_index=-1,
            step_id="",
            run_id=self._run_id,
        )

    def _run_step(
        self,
        step_index: int,
        step: dict[str, Any],
        events_path: Path,
    ) -> None:
        step_id = str(step.get("id", f"step_{step_index}")).strip() or f"step_{step_index}"
        self._emit_event(events_path, "started", step_index, step_id, {})

        seq = step_index + 1
        cmd = {
            "schema": "pointer_gpf.flow_command.v1",
            "run_id": self._run_id,
            "seq": seq,
            "step_index": step_index,
            "step_id": step_id,
            "step": self._step_for_bridge(step),
        }
        bridge = self._bridge_dir()
        bridge.mkdir(parents=True, exist_ok=True)
        rsp_path = self._response_path()
        try:
            if rsp_path.exists():
                rsp_path.unlink()
        except OSError:
            pass
        self._command_path().write_text(json.dumps(cmd, ensure_ascii=False), encoding="utf-8")

        timeout_ms = max(1, int(self.options.step_timeout_ms))
        deadline = time.monotonic() + timeout_ms / 1000.0
        try:
            response = self._wait_for_response(seq, deadline)
        except FlowExecutionTimeout as exc:
            exc.step_index = step_index
            exc.step_id = step_id
            raise

        ok = bool(response.get("ok", False))
        self._emit_event(
            events_path,
            "result",
            step_index,
            step_id,
            {"bridge_ok": ok, "bridge_message": str(response.get("message", ""))},
        )
        verified = ok
        self._emit_event(
            events_path,
            "verify",
            step_index,
            step_id,
            {"verified": verified},
        )
        if self.options.fail_fast and not ok:
            raise FlowExecutionStepFailed(
                f"bridge reported failure for step {step_id!r}",
                step_index=step_index,
                step_id=step_id,
                run_id=self._run_id,
            )

    def run(self, flow_payload: dict[str, Any]) -> dict[str, Any]:
        steps = flow_payload.get("steps")
        if not isinstance(steps, list):
            steps = []
        flow_id = str(flow_payload.get("flowId", "")).strip()

        report_dir = self.options.report_dir.resolve()
        report_dir.mkdir(parents=True, exist_ok=True)
        events_path = report_dir / f"flow_run_events_{self._slug}.ndjson"
        report_path = report_dir / f"flow_run_report_{self._slug}.json"

        if events_path.exists():
            events_path.unlink()

        phase_coverage: dict[str, int] = {"started": 0, "result": 0, "verify": 0}
        status = "completed"
        reraise: BaseException | None = None

        try:
            for idx, raw in enumerate(steps):
                if not isinstance(raw, dict):
                    continue
                self._run_step(idx, raw, events_path)
        except FlowExecutionTimeout as exc:
            status = "timeout"
            reraise = exc
        except FlowExecutionStepFailed as exc:
            status = "failed"
            reraise = exc

        if events_path.is_file():
            for line in events_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ph = str(ev.get("phase", ""))
                if ph in phase_coverage:
                    phase_coverage[ph] += 1

        report: dict[str, Any] = {
            "run_id": self._run_id,
            "status": status,
            "step_count": len([s for s in steps if isinstance(s, dict)]),
            "phase_coverage": phase_coverage,
            "events_file": str(events_path),
            "report_file": str(report_path),
            "flow_file": str(self.options.flow_file.resolve()),
            "flow_id": flow_id,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if reraise is not None:
            if isinstance(reraise, (FlowExecutionTimeout, FlowExecutionStepFailed)):
                reraise.report = report
            raise reraise
        return report
