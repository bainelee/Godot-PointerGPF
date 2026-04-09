from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from artifact_service import build_test_report_payload, load_flow_report
from flow_timeline_reader import read_flow_timeline_payload
from runner import GameTestRunner, RunRequest
from scenario_registry import get_default_scenario_by_system, get_scenario_by_name, list_scenarios
from server_common import first_failure_reason, load_report, primary_failure_summary, resolve_godot_bin, to_posix
from server_errors import AppError


class CoreHandlersMixin:
    default_project_root: Path

    def __init__(self, default_project_root: Path) -> None:
        self.default_project_root = default_project_root.resolve()

    def list_test_scenarios(self, _arguments: dict[str, Any]) -> dict[str, Any]:
        scenarios = list_scenarios()
        for scenario in scenarios:
            if "scene" in scenario:
                scenario["scene"] = to_posix(scenario["scene"])
        return {"scenarios": scenarios}

    def run_game_test(self, arguments: dict[str, Any]) -> dict[str, Any]:
        system = str(arguments.get("system", "")).strip()
        if not system:
            raise AppError("INVALID_ARGUMENT", "system is required")
        scenario = arguments.get("scenario")
        scenario_name: str
        if scenario:
            scenario_name = str(scenario)
            if not get_scenario_by_name(scenario_name):
                raise AppError("UNKNOWN_SCENARIO", f"unknown scenario: {scenario_name}")
        else:
            default_scenario = get_default_scenario_by_system(system)
            if not default_scenario:
                raise AppError("UNKNOWN_SYSTEM", f"no default scenario for system: {system}")
            scenario_name = default_scenario.name
        environment = arguments.get("environment", {}) or {}
        execution = arguments.get("execution", {}) or {}
        mode = str(environment.get("mode", "vm"))
        if mode not in {"vm", "local", "headless"}:
            raise AppError("INVALID_ARGUMENT", f"unsupported mode: {mode}")
        timeout_sec = int(execution.get("timeoutSec", 300))
        if timeout_sec <= 0:
            raise AppError("INVALID_ARGUMENT", "execution.timeoutSec must be > 0")
        retry = int(execution.get("retry", 0))
        if retry < 0:
            raise AppError("INVALID_ARGUMENT", "execution.retry must be >= 0")
        project_root_raw = arguments.get("project_root", str(self.default_project_root))
        project_root = Path(str(project_root_raw)).resolve()
        if not project_root.exists():
            raise AppError("INVALID_ARGUMENT", f"project_root not found: {project_root}")
        requested_godot_bin = str(arguments.get("godot_bin", "godot4"))
        resolved_godot_bin, resolution_meta = resolve_godot_bin(
            requested=requested_godot_bin,
            strict=bool(arguments.get("strict_godot_bin", False)),
            allow_unresolved=bool(arguments.get("dry_run", False)),
            project_root=project_root,
        )
        req = RunRequest(
            system=system,
            project_root=project_root,
            scenario=scenario_name,
            profile=str(arguments.get("profile", "smoke")),
            mode=mode,
            timeout_sec=timeout_sec,
            retry=retry,
            clean_save_slots=bool(execution.get("cleanSaveSlots", True)),
            godot_bin=resolved_godot_bin,
            scene=arguments.get("scene"),
            extra_args=list(arguments.get("extra_args", [])),
            dry_run=bool(arguments.get("dry_run", False)),
            enable_test_driver=bool(arguments.get("enable_test_driver", False)),
            flow_steps=list(arguments.get("flow_steps", [])),
            flow_step_timeout_sec=int(arguments.get("flow_step_timeout_sec", 15)),
            allow_parallel=bool(arguments.get("allow_parallel", False)),
        )
        runner = GameTestRunner(project_root=project_root)
        result = runner.run(req)
        return {
            "run_id": result.run_id,
            "status": result.status,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "artifact_root": to_posix(result.artifact_root),
            "exit_code": result.exit_code,
            "command": [to_posix(c) for c in result.command],
            "godot_bin_requested": requested_godot_bin,
            "godot_bin_resolved": resolved_godot_bin,
            "godot_bin_resolution": resolution_meta,
        }

    def _resolve_run_root(self, run_id: str, arguments: dict[str, Any]) -> Path:
        run_id = run_id.strip()
        if not run_id:
            raise AppError("INVALID_ARGUMENT", "run_id is required")
        artifact_base_raw = arguments.get("artifact_base")
        artifact_base = (
            Path(str(artifact_base_raw)).resolve()
            if artifact_base_raw
            else self.default_project_root / "artifacts" / "test-runs"
        )
        run_root = artifact_base / run_id
        if not run_root.exists():
            raise AppError("NOT_FOUND", f"run artifacts not found: {run_root}")
        return run_root

    @staticmethod
    def _status_file(run_root: Path) -> Path:
        return run_root / "fix_loop_state.json"

    def _save_fix_loop_state(self, run_root: Path, state: dict[str, Any]) -> None:
        self._status_file(run_root).write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_fix_loop_state(self, run_root: Path) -> dict[str, Any]:
        state_path = self._status_file(run_root)
        if not state_path.exists():
            return {}
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def _load_status_by_run_id(self, run_id: str, arguments: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
        run_root = self._resolve_run_root(run_id, arguments)
        state = self._load_fix_loop_state(run_root)
        if state:
            return run_root, state
        report = load_report(run_root)
        primary_failure = primary_failure_summary(report)
        failures = report.get("failures", []) if isinstance(report.get("failures", []), list) else []
        has_failures = len(failures) > 0
        fallback = {
            "version": 2,
            "run_id": run_id,
            "artifact_root": to_posix(run_root),
            "status": "exhausted" if has_failures else "resolved",
            "current_step": "completed",
            "fix_loop_round": 0,
            "approval_required": False,
            "fix_loop": {
                "enabled": False,
                "max_rounds": 0,
                "rounds_executed": 0,
                "approval_required": False,
                "status": "not_enabled",
                "rounds": [
                    {
                        "round": 0,
                        "run_id": run_id,
                        "status": "failed" if has_failures else "passed",
                        "reason": first_failure_reason(report),
                        "primary_failure": primary_failure,
                    }
                ],
            },
        }
        return run_root, fallback

    def get_test_artifacts(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        run_root = self._resolve_run_root(run_id, arguments)
        logs = sorted([p.relative_to(run_root).as_posix() for p in (run_root / "logs").glob("*") if p.is_file()])
        screenshots = sorted(
            [p.relative_to(run_root).as_posix() for p in (run_root / "screenshots").glob("*") if p.is_file()]
        )
        save_snapshots = sorted(
            [p.relative_to(run_root).as_posix() for p in (run_root / "save_snapshots").glob("*") if p.is_file()]
        )
        report_json = (run_root / "report.json").relative_to(run_root).as_posix() if (run_root / "report.json").exists() else ""
        report_md = (run_root / "report.md").relative_to(run_root).as_posix() if (run_root / "report.md").exists() else ""
        junit_xml = (run_root / "junit.xml").relative_to(run_root).as_posix() if (run_root / "junit.xml").exists() else ""
        flow_report_json = (
            (run_root / "flow_report.json").relative_to(run_root).as_posix() if (run_root / "flow_report.json").exists() else ""
        )
        step_timeline_json = (
            (run_root / "step_timeline.json").relative_to(run_root).as_posix()
            if (run_root / "step_timeline.json").exists()
            else ""
        )
        driver_flow_json = (
            (run_root / "logs" / "driver_flow.json").relative_to(run_root).as_posix()
            if (run_root / "logs" / "driver_flow.json").exists()
            else ""
        )
        failure_summary_json = (
            (run_root / "failure_summary.json").relative_to(run_root).as_posix()
            if (run_root / "failure_summary.json").exists()
            else ""
        )
        return {
            "run_id": run_id,
            "artifact_root": to_posix(run_root),
            "logs": logs,
            "screenshots": screenshots,
            "save_snapshots": save_snapshots,
            "report_json": report_json,
            "report_md": report_md,
            "junit_xml": junit_xml,
            "flow_report_json": flow_report_json,
            "step_timeline_json": step_timeline_json,
            "driver_flow_json": driver_flow_json,
            "failure_summary_json": failure_summary_json,
            "key_files": [
                path
                for path in [
                    report_json,
                    report_md,
                    junit_xml,
                    flow_report_json,
                    step_timeline_json,
                    driver_flow_json,
                    failure_summary_json,
                ]
                if path
            ],
        }

    def get_test_report(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        fmt = str(arguments.get("format", "json")).strip().lower()
        if fmt not in {"json", "md"}:
            raise AppError("INVALID_ARGUMENT", "format must be json or md")
        run_root = self._resolve_run_root(run_id, arguments)
        payload = build_test_report_payload(run_id=run_id, run_root=run_root, fmt=fmt)
        if payload:
            return payload
        if fmt == "json":
            raise AppError("NOT_FOUND", f"missing report file: {run_root / 'report.json'}")
        raise AppError("NOT_FOUND", f"missing report file: {run_root / 'report.md'}")

    def get_flow_timeline(self, arguments: dict[str, Any]) -> dict[str, Any]:
        run_id = str(arguments.get("run_id", "")).strip()
        if not run_id:
            raise AppError("INVALID_ARGUMENT", "run_id is required")
        view = str(arguments.get("view", "full")).strip().lower() or "full"
        if view not in {"full", "chat"}:
            raise AppError("INVALID_ARGUMENT", "view must be full or chat")
        recent_steps_limit = int(arguments.get("recent_steps_limit", 3))
        chat_mode = str(arguments.get("chat_mode", "normal")).strip().lower() or "normal"
        if chat_mode not in {"normal", "short"}:
            raise AppError("INVALID_ARGUMENT", "chat_mode must be normal or short")
        run_root = self._resolve_run_root(run_id, arguments)
        report = load_report(run_root)
        flow_report = load_flow_report(run_root)
        return read_flow_timeline_payload(
            run_id=run_id,
            run_root=run_root,
            report=report if isinstance(report, dict) else {},
            flow_report=flow_report if isinstance(flow_report, dict) else {},
            to_posix=to_posix,
            view=view,
            recent_steps_limit=recent_steps_limit,
            chat_mode=chat_mode,
        )

    def check_test_runner_environment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested_godot_bin = str(arguments.get("godot_bin", "godot4"))
        strict = bool(arguments.get("strict_godot_bin", True))
        project_root_raw = arguments.get("project_root", str(self.default_project_root))
        project_root = Path(str(project_root_raw)).resolve()
        checks: list[dict[str, Any]] = []
        recommendations: list[str] = []
        ok = True
        try:
            resolved_godot_bin, resolution = resolve_godot_bin(
                requested=requested_godot_bin,
                strict=strict,
                allow_unresolved=False,
                project_root=project_root if project_root.is_dir() else None,
            )
            checks.append(
                {
                    "id": "godot_bin",
                    "status": "passed",
                    "message": "Godot executable resolved",
                    "resolved": resolved_godot_bin,
                    "resolution": resolution,
                }
            )
        except AppError as exc:
            ok = False
            checks.append(
                {
                    "id": "godot_bin",
                    "status": "failed",
                    "message": exc.message,
                    "details": exc.details or {},
                }
            )
            recommendations.append("Set GODOT_BIN to a valid Godot executable path, then open a new shell session.")
            recommendations.append(
                "PowerShell: setx GODOT_BIN \"D:\\GODOT\\Godot_v4.6.1-stable_win64.exe\\Godot_v4.6.1-stable_win64.exe\""
            )
            recommendations.append(
                "Or copy tools/game-test-runner/config/godot_executable.example.json to godot_executable.json and set godot_executable."
            )
            resolved_godot_bin = ""
            resolution = {}
        if project_root.exists() and project_root.is_dir():
            checks.append({"id": "project_root", "status": "passed", "message": "project_root exists", "path": to_posix(project_root)})
        else:
            ok = False
            checks.append(
                {
                    "id": "project_root",
                    "status": "failed",
                    "message": f"project_root not found: {project_root}",
                    "path": to_posix(project_root),
                }
            )
        return {
            "ok": ok,
            "godot_bin_requested": requested_godot_bin,
            "godot_bin_resolved": resolved_godot_bin,
            "godot_bin_resolution": resolution,
            "checks": checks,
            "recommendations": recommendations,
            "ci_ready": ok,
        }
