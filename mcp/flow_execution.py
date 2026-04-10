"""MCP-side flow runner: file bridge (command.json / response.json) and three-phase event logging."""

from __future__ import annotations

import json
import re
import sys
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


class FlowExecutionEngineStalled(Exception):
    """runtime_diagnostics.json reports error/fatal while waiting for file bridge response."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any], run_id: str) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics
        self.run_id = run_id
        self.step_index = -1
        self.step_id = ""
        self.report: dict[str, Any] | None = None


@dataclass
class FlowRunOptions:
    project_root: Path
    flow_file: Path
    report_dir: Path
    step_timeout_ms: int = 30_000
    run_id: str | None = None
    fail_fast: bool = True
    shell_report: bool = False
    runtime_meta: dict[str, Any] | None = None
    observe_engine_errors: bool = True


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

    def _runtime_diagnostics_path(self) -> Path:
        return self._bridge_dir() / "runtime_diagnostics.json"

    def _read_blocking_diagnostics(self) -> dict[str, Any] | None:
        if not bool(self.options.observe_engine_errors):
            return None
        path = self._runtime_diagnostics_path()
        if not path.is_file():
            return None
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        sev = str(data.get("severity", "")).strip().lower()
        if sev in ("error", "fatal"):
            return data
        return None

    def _append_ndjson(self, path: Path, obj: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def _local_shell_ts(self) -> str:
        return datetime.now().strftime("%Y-%m-%d T %H:%M:%S")

    def _build_step_semantics(self, step_id: str, step_action: str, step: dict[str, Any]) -> tuple[str, str]:
        canonical: dict[str, tuple[str, str]] = {
            "launch_game": ("正在启动游戏运行会话", "进入可执行基础测试的游戏运行态."),
            "wait_bootstrap": ("正在等待游戏主场景初始化完成", "主场景初始化完成并可交互."),
            "enter_game": ("正在进入游戏主流程", "进入可操作的游戏主流程."),
            "wait_enter_game": ("正在等待游戏内HUD稳定显示", "游戏内HUD已显示并可继续执行."),
            "load_game_smoke": ("正在从存档0直接加载游戏主场景", "复现用户当前存档状态,不覆盖现有进度."),
            "assert_load_success": ("正在验证存档加载结果", "确认存档加载成功且当前状态可继续测试."),
            "snapshot_end": ("正在记录流程结束快照", "保留流程结束证据以便复核."),
        }
        if step_id in canonical:
            return canonical[step_id]

        hint = str(step.get("hint", "")).strip()
        target_hint = ""
        target = step.get("target")
        if isinstance(target, dict):
            target_hint = str(target.get("hint", "")).strip()
        until = step.get("until")
        until_hint = ""
        if isinstance(until, dict):
            until_hint = str(until.get("hint", "")).strip()

        action = step_action.lower()
        action_text = {
            "launchgame": "启动游戏",
            "click": "点击交互",
            "wait": "等待状态推进",
            "check": "执行状态检查",
            "snapshot": "记录快照",
            "movemouse": "移动虚拟鼠标",
            "drag": "执行拖拽操作",
        }.get(action, "执行测试动作")
        focus = target_hint or until_hint or hint or step_id
        task_text = f"正在{action_text}: {focus}"
        target_text = (until_hint or target_hint or hint or "完成当前步骤目标并保持流程可继续执行").rstrip(".")
        return task_text, f"{target_text}."

    def _emit_event(self, events_path: Path, phase: str, step_index: int, step_id: str, extra: dict[str, Any] | None = None) -> None:
        row: dict[str, Any] = {
            "phase": phase,
            "run_id": self._run_id,
            "step_index": step_index,
            "step_id": step_id,
            "ts": _utc_iso(),
            "shell_report": bool(self.options.shell_report),
        }
        if extra:
            row.update(extra)
        self._append_ndjson(events_path, row)
        if bool(self.options.shell_report):
            print(f"[GPF-FLOW-TS] {self._local_shell_ts()}", file=sys.stderr, flush=True)
            task_text = str(row.get("task_text", "")).strip() or "正在执行测试步骤"
            target_text = str(row.get("target_text", "")).strip() or "完成当前步骤目标并保持流程可继续执行."
            if phase == "started":
                semantic = f"开始执行:{task_text}"
            elif phase == "result":
                semantic = f"执行结果:{task_text}({'通过' if bool(row.get('bridge_ok', False)) else '失败'})"
            else:
                semantic = f"验证结论:{'通过' if bool(row.get('verified', False)) else '失败'}-目标:{target_text}"
            print(semantic, file=sys.stderr, flush=True)

    def _step_for_bridge(self, step: dict[str, Any]) -> dict[str, Any]:
        out = dict(step)
        out.pop("chat_contract", None)
        return out

    def _wait_for_response(self, seq: int, deadline: float) -> dict[str, Any]:
        rsp = self._response_path()
        while time.monotonic() < deadline:
            blocking = self._read_blocking_diagnostics()
            if blocking is not None:
                raise FlowExecutionEngineStalled(
                    "runtime diagnostics reported error/fatal while waiting for bridge response",
                    diagnostics=blocking,
                    run_id=self._run_id,
                )
            if rsp.is_file():
                try:
                    payload = json.loads(rsp.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    time.sleep(0.02)
                    continue
                if not isinstance(payload, dict):
                    time.sleep(0.02)
                    continue
                try:
                    response_seq = int(payload.get("seq", -1))
                except (TypeError, ValueError):
                    # Ignore malformed bridge responses and keep waiting for a valid one.
                    time.sleep(0.02)
                    continue
                if response_seq == seq and str(payload.get("run_id", "")) == self._run_id:
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
    ) -> bool:
        step_id = str(step.get("id", f"step_{step_index}")).strip() or f"step_{step_index}"
        step_action = str(step.get("action", "")).strip()
        task_text, target_text = self._build_step_semantics(step_id, step_action, step)
        semantic_base = {"task_text": task_text, "target_text": target_text}
        self._emit_event(events_path, "started", step_index, step_id, semantic_base)

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
        except FlowExecutionEngineStalled as exc:
            exc.step_index = step_index
            exc.step_id = step_id
            raise
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
            {**semantic_base, "bridge_ok": ok, "bridge_message": str(response.get("message", ""))},
        )
        verified = ok
        self._emit_event(
            events_path,
            "verify",
            step_index,
            step_id,
            {**semantic_base, "verified": verified},
        )
        if self.options.fail_fast and not ok:
            raise FlowExecutionStepFailed(
                f"bridge reported failure for step {step_id!r}",
                step_index=step_index,
                step_id=step_id,
                run_id=self._run_id,
            )
        return ok

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
        status = "passed"
        reraise: BaseException | None = None
        has_step_failure = False

        try:
            for idx, raw in enumerate(steps):
                if not isinstance(raw, dict):
                    continue
                ok = self._run_step(idx, raw, events_path)
                if not ok:
                    has_step_failure = True
        except FlowExecutionStepFailed as exc:
            status = "failed"
            reraise = exc
        except FlowExecutionEngineStalled as exc:
            status = "engine_stalled"
            reraise = exc
        except FlowExecutionTimeout as exc:
            status = "timeout"
            reraise = exc
        else:
            if has_step_failure:
                status = "failed"

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
            "shell_report": bool(self.options.shell_report),
        }
        runtime_meta = self.options.runtime_meta if isinstance(self.options.runtime_meta, dict) else {}
        report.update(
            {
                "runtime_mode": str(runtime_meta.get("runtime_mode", "unknown")),
                "runtime_entry": str(runtime_meta.get("runtime_entry", "unknown")),
                "runtime_gate_passed": bool(runtime_meta.get("runtime_gate_passed", False)),
                "input_mode": str(runtime_meta.get("input_mode", "in_engine_virtual_input")),
                "os_input_interference": bool(runtime_meta.get("os_input_interference", False)),
                "step_broadcast_summary": {
                    "protocol_mode": "three_phase",
                    "fail_fast_on_verify": bool(self.options.fail_fast),
                },
            }
        )
        if isinstance(reraise, FlowExecutionEngineStalled):
            report["runtime_diagnostics"] = reraise.diagnostics
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if reraise is not None:
            if isinstance(reraise, (FlowExecutionTimeout, FlowExecutionStepFailed, FlowExecutionEngineStalled)):
                reraise.report = report
            raise reraise
        return report
