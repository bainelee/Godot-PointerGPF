#!/usr/bin/env python3
"""Run gameplay flows through TestDriver-enabled runner."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flow_parser import parse_flow_file
from runner import GameTestRunner, RunRequest


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _replace_vars(value: Any, env: dict[str, Any]) -> Any:
    if isinstance(value, str):
        out = value
        for k, v in env.items():
            out = out.replace("${%s}" % k, str(v))
        return out
    if isinstance(value, list):
        return [_replace_vars(x, env) for x in value]
    if isinstance(value, dict):
        return {k: _replace_vars(v, env) for k, v in value.items()}
    return value


def _expand_steps(flow: dict[str, Any], flow_file: Path, inherited_env: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    env = dict(inherited_env or {})
    env.update(flow.get("env", {}) if isinstance(flow.get("env", {}), dict) else {})
    out: list[dict[str, Any]] = []
    base_dir = flow_file.parent
    for step in flow.get("steps", []):
        resolved_step = _replace_vars(step, env)
        if str(resolved_step.get("action", "")) == "runSubflow":
            subfile = base_dir / str(resolved_step.get("file", ""))
            subflow = parse_flow_file(subfile)
            sub_env = dict(env)
            if isinstance(resolved_step.get("env", {}), dict):
                sub_env.update(resolved_step.get("env", {}))
            out.extend(_expand_steps(subflow, subfile, inherited_env=sub_env))
            continue
        out.append(resolved_step)
    return out


def _resolve_step_timeout_sec(step: dict[str, Any], default_timeout_sec: int) -> int:
    step_timeout = int(step.get("timeoutSec", default_timeout_sec))
    if str(step.get("action", "")).strip() != "wait":
        return step_timeout

    # Keep driver timeout >= wait condition timeout (plus small polling buffer).
    until_cfg = step.get("until", {})
    timeout_ms = int(step.get("timeoutMs", 0))
    if isinstance(until_cfg, dict):
        timeout_ms = max(timeout_ms, int(until_cfg.get("timeoutMs", 0)))
    if timeout_ms <= 0:
        return step_timeout

    wait_timeout_sec = (timeout_ms + 999) // 1000 + 2
    return max(step_timeout, wait_timeout_sec)


def _to_driver_steps(expanded_steps: list[dict[str, Any]], default_timeout_sec: int) -> list[dict[str, Any]]:
    driver_steps: list[dict[str, Any]] = []
    for step in expanded_steps:
        action = str(step.get("action", "")).strip()
        if not action:
            continue
        params = dict(step)
        params.pop("id", None)
        params.pop("action", None)
        params.pop("timeoutSec", None)
        driver_steps.append(
            {
                "id": step.get("id", ""),
                "action": action,
                "params": params,
                "timeoutSec": _resolve_step_timeout_sec(step, default_timeout_sec),
            }
        )
    return driver_steps


def _to_rel_run_path(run_root: Path, raw_path: str) -> str:
    text = str(raw_path or "").strip()
    if not text:
        return ""
    if text.startswith("user://"):
        name = Path(text.replace("user://", "", 1)).name
        if not name:
            return text
        candidate = run_root / "screenshots" / name
        if candidate.exists():
            return candidate.relative_to(run_root).as_posix()
        return text
    p = Path(text)
    if p.is_absolute():
        try:
            return p.relative_to(run_root).as_posix()
        except ValueError:
            return text
    candidate = run_root / p
    if candidate.exists():
        return candidate.relative_to(run_root).as_posix()
    return text.replace("\\", "/")


def _flow_step_description(step: dict[str, Any]) -> str:
    custom = str(step.get("description", "")).strip()
    if custom:
        return custom
    action = str(step.get("action", "")).strip()
    params = step.get("params", {})
    if not isinstance(params, dict):
        params = {}
    if action == "click":
        node_path = str(params.get("nodePath", params.get("node_path", ""))).strip()
        return "Click target node" if node_path else "Click action"
    if action == "wait":
        return "Wait until condition met"
    if action == "check":
        kind = str(params.get("kind", "")).strip()
        return f"Check assertion ({kind})" if kind else "Check assertion"
    if action == "screenshot":
        return "Capture validation screenshot"
    if action == "sleep":
        return "Wait for fixed duration"
    return action or "flow step"


def _build_step_timeline(
    run_root: Path,
    flow_id: str,
    run_id: str,
    flow_steps: list[dict[str, Any]],
    driver_steps: list[dict[str, Any]],
    started_at_iso: str,
    finished_at_iso: str,
    run_status: str,
) -> dict[str, Any]:
    driver_flow_path = run_root / "logs" / "driver_flow.json"
    driver_flow = {}
    if driver_flow_path.exists():
        try:
            driver_flow = json.loads(driver_flow_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            driver_flow = {}
    driver_results = driver_flow.get("steps", []) if isinstance(driver_flow, dict) else []
    if not isinstance(driver_results, list):
        driver_results = []

    flow_step_map: dict[str, dict[str, Any]] = {}
    for idx, step in enumerate(flow_steps):
        if not isinstance(step, dict):
            continue
        sid = str(step.get("id", "")).strip() or f"step_{idx + 1:02d}"
        flow_step_map[sid] = step

    driver_step_map: dict[str, dict[str, Any]] = {}
    for idx, step in enumerate(driver_steps):
        if not isinstance(step, dict):
            continue
        sid = str(step.get("id", "")).strip() or f"step_{idx + 1:02d}"
        driver_step_map[sid] = step

    try:
        cursor = datetime.fromisoformat(started_at_iso)
    except ValueError:
        cursor = datetime.now(timezone.utc)

    timeline_steps: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, result in enumerate(driver_results):
        if not isinstance(result, dict):
            continue
        sid = str(result.get("step_id", "")).strip() or f"step_{idx + 1:02d}"
        seen_ids.add(sid)
        driver_step_def = driver_step_map.get(sid, {})
        flow_step_def = flow_step_map.get(sid, {})
        action = str(result.get("action", "")).strip() or str(driver_step_def.get("action", "")).strip()
        duration_ms = int(result.get("duration_ms", 0)) if str(result.get("duration_ms", "")).strip() else 0
        started_at = cursor
        finished_at = cursor + timedelta(milliseconds=max(0, duration_ms))
        cursor = finished_at

        status = str(result.get("status", "unknown")).strip()
        normalized_status = "passed" if status == "passed" else ("failed" if status == "failed" else "unknown")
        response = result.get("response", {})
        if not isinstance(response, dict):
            response = {}
        error_raw = response.get("error", {})
        if not isinstance(error_raw, dict):
            error_raw = {}
        actual = str(error_raw.get("message", "")).strip() or str(result.get("error", "")).strip()
        if not actual:
            actual = "ok" if normalized_status == "passed" else "step failed"

        evidence_files: list[str] = ["logs/driver_flow.json"]
        screenshot = str(response.get("screenshot", "")).strip()
        screenshot_rel = _to_rel_run_path(run_root, screenshot)
        if screenshot_rel:
            evidence_files.append(screenshot_rel)
        data_raw = response.get("data", {})
        if isinstance(data_raw, dict):
            for key in ("path", "screenshot", "output", "report"):
                rel = _to_rel_run_path(run_root, str(data_raw.get(key, "")).strip())
                if rel:
                    evidence_files.append(rel)
        if normalized_status == "failed":
            evidence_files.extend(["report.json", "failure_summary.json"])
        evidence_files = list(dict.fromkeys([x for x in evidence_files if x]))

        timeline_steps.append(
            {
                "index": idx,
                "step_id": sid,
                "action": action,
                "description": _flow_step_description(
                    flow_step_def if isinstance(flow_step_def, dict) and flow_step_def else driver_step_def
                ),
                "status": normalized_status,
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_ms": max(0, duration_ms),
                "expected": "driver step status == ok",
                "actual": actual,
                "evidence_files": evidence_files,
            }
        )

    total_steps = len(driver_steps)
    for idx, step in enumerate(driver_steps):
        if not isinstance(step, dict):
            continue
        sid = str(step.get("id", "")).strip() or f"step_{idx + 1:02d}"
        if sid in seen_ids:
            continue
        timeline_steps.append(
            {
                "index": idx,
                "step_id": sid,
                "action": str(step.get("action", "")).strip(),
                "description": _flow_step_description(step),
                "status": "skipped",
                "started_at": None,
                "finished_at": None,
                "duration_ms": 0,
                "expected": "step executes after previous steps pass",
                "actual": "not executed because flow ended early",
                "evidence_files": ["logs/driver_flow.json", "report.json", "failure_summary.json"],
            }
        )

    timeline_steps.sort(key=lambda s: int(s.get("index", 0)))
    failed = sum(1 for s in timeline_steps if str(s.get("status", "")) == "failed")
    passed = sum(1 for s in timeline_steps if str(s.get("status", "")) == "passed")
    skipped = sum(1 for s in timeline_steps if str(s.get("status", "")) == "skipped")
    return {
        "flow_id": flow_id,
        "run_id": run_id,
        "status": run_status,
        "started_at": started_at_iso,
        "finished_at": finished_at_iso,
        "generated_at": _utc_now_iso(),
        "summary": {
            "total": total_steps,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
        "steps": timeline_steps,
    }


def execute_flow_file(
    flow_file: Path,
    project_root: Path,
    godot_bin: str,
    timeout_sec: int,
    dry_run: bool,
    driver_ready_timeout_sec: int | None = None,
    driver_no_activity_timeout_sec: int | None = None,
    run_id: str | None = None,
    allow_parallel: bool = False,
) -> tuple[dict, int]:
    flow = parse_flow_file(flow_file)
    flow_steps = _expand_steps(flow, flow_file)
    default_step_timeout_sec = int(flow.get("flowStepTimeoutSec", 15))
    driver_steps = _to_driver_steps(flow_steps, default_timeout_sec=default_step_timeout_sec)
    if not dry_run and driver_steps:
        print(
            "gameplayflow: flow_runner.py has no per-step shell broadcast; "
            "use tools/game-test-runner/scripts/run_gameplay_stepwise_chat.py "
            "or run_gameplay_stepwise_chat.ps1 (see docs/testing/README.md).",
            file=sys.stderr,
        )
    system = str(flow.get("system", "gameplay"))
    scene = flow.get("scene")
    scenario = flow.get("scenario")
    screenshot_prefix = str(flow.get("screenshotPrefix", "")).strip() or None

    req = RunRequest(
        system=system,
        project_root=project_root,
        scenario=str(scenario) if scenario else None,
        profile=str(flow.get("profile", "flow")),
        mode=str(flow.get("mode", "local")),
        timeout_sec=timeout_sec,
        retry=int(flow.get("retry", 0)),
        godot_bin=godot_bin,
        scene=str(scene) if scene else None,
        dry_run=dry_run,
        screenshot_prefix=screenshot_prefix,
        enable_test_driver=True,
        flow_steps=driver_steps,
        flow_step_timeout_sec=default_step_timeout_sec,
        driver_ready_timeout_sec=(
            min(20, int(driver_ready_timeout_sec))
            if driver_ready_timeout_sec is not None
            else min(20, int(flow.get("driverReadyTimeoutSec", 20)))
        ),
        driver_no_activity_timeout_sec=(
            int(driver_no_activity_timeout_sec)
            if driver_no_activity_timeout_sec is not None
            else int(flow.get("driverNoActivityTimeoutSec", 5))
        ),
        reload_project_before_run=bool(flow.get("reloadProjectBeforeRun", True)),
        reload_timeout_sec=int(flow.get("reloadTimeoutSec", 20)),
        requested_run_id=str(run_id).strip() if run_id else None,
        step_prepare_pause_ms=int(flow.get("stepPreparePauseMs", 0)),
        step_verify_pause_ms=int(flow.get("stepVerifyPauseMs", flow.get("stepDebugPauseMs", 0))),
        allow_parallel=bool(allow_parallel),
    )

    started_at = _utc_now_iso()
    if run_id:
        pre_run_root = project_root / "artifacts" / "test-runs" / str(run_id).strip()
        pre_run_root.mkdir(parents=True, exist_ok=True)
        pre_flow_report = {
            "flow_id": flow.get("flowId", flow_file.stem),
            "flow_file": str(flow_file),
            "status": "running",
            "started_at": started_at,
            "finished_at": "",
            "run_id": str(run_id).strip(),
            "driver_steps": driver_steps,
        }
        (pre_run_root / "flow_report.json").write_text(
            json.dumps(pre_flow_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    runner = GameTestRunner(project_root=project_root)
    result = runner.run(req)
    finished_at = _utc_now_iso()
    run_root = Path(result.artifact_root)
    flow_report = {
        "flow_id": flow.get("flowId", flow_file.stem),
        "flow_file": str(flow_file),
        "status": "passed" if result.status == "finished" else "failed",
        "started_at": started_at,
        "finished_at": finished_at,
        "run_id": result.run_id,
        "driver_steps": driver_steps,
    }
    flow_report_path = run_root / "flow_report.json"
    flow_report_path.write_text(json.dumps(flow_report, ensure_ascii=False, indent=2), encoding="utf-8")
    step_timeline = _build_step_timeline(
        run_root=run_root,
        flow_id=str(flow_report["flow_id"]),
        run_id=str(result.run_id),
        flow_steps=flow_steps,
        driver_steps=driver_steps,
        started_at_iso=started_at,
        finished_at_iso=finished_at,
        run_status=str(flow_report["status"]),
    )
    step_timeline_path = run_root / "step_timeline.json"
    step_timeline_path.write_text(json.dumps(step_timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    failure_summary_path = run_root / "failure_summary.json"
    if failure_summary_path.exists():
        try:
            failure_summary = json.loads(failure_summary_path.read_text(encoding="utf-8"))
            if isinstance(failure_summary, dict):
                key_files = failure_summary.get("key_files", [])
                if not isinstance(key_files, list):
                    key_files = []
                flow_rel = "flow_report.json"
                if flow_rel not in key_files:
                    key_files.append(flow_rel)
                timeline_rel = "step_timeline.json"
                if timeline_rel not in key_files:
                    key_files.append(timeline_rel)
                failure_summary["key_files"] = key_files
                failure_summary_path.write_text(
                    json.dumps(failure_summary, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except json.JSONDecodeError:
            pass
    report_path = run_root / "report.json"
    flow_report_str = str(flow_report_path)
    payload = {
        "flow_id": flow_report["flow_id"],
        "status": flow_report["status"],
        "run_id": result.run_id,
        "artifact_root": str(run_root),
        "flow_report": flow_report_str,
        "flow_report_file": flow_report_str,
        "report_file": str(report_path),
        "step_timeline": str(step_timeline_path),
    }
    return payload, 0 if result.status == "finished" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run gameplay flow file.")
    parser.add_argument("--flow-file", required=True, help="Flow file path (json/yaml)")
    parser.add_argument("--project-root", required=True, help="Project root path")
    parser.add_argument("--godot-bin", required=True, help="Godot executable path")
    parser.add_argument("--timeout-sec", type=int, default=300, help="Whole run timeout")
    parser.add_argument("--dry-run", action="store_true", help="Skip actual Godot run")
    parser.add_argument(
        "--driver-ready-timeout-sec",
        type=int,
        default=None,
        help="Override TestDriver ready timeout seconds",
    )
    parser.add_argument(
        "--driver-no-activity-timeout-sec",
        type=int,
        default=None,
        help="Override no-activity kill timeout seconds",
    )
    parser.add_argument("--run-id", default=None, help="Optional fixed run_id for live session polling")
    parser.add_argument("--allow-parallel", action="store_true", help="Allow multiple test runtimes concurrently")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload, code = execute_flow_file(
        flow_file=Path(args.flow_file).resolve(),
        project_root=Path(args.project_root).resolve(),
        godot_bin=args.godot_bin,
        timeout_sec=args.timeout_sec,
        dry_run=args.dry_run,
        driver_ready_timeout_sec=args.driver_ready_timeout_sec,
        driver_no_activity_timeout_sec=args.driver_no_activity_timeout_sec,
        run_id=args.run_id,
        allow_parallel=bool(args.allow_parallel),
    )
    print(json.dumps(payload, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

