#!/usr/bin/env python3
"""Minimal game test runner skeleton (Step 2)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from xml.sax.saxutils import escape
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from driver_client import DriverClient
from runtime_lock import acquire_runtime_lock, release_runtime_lock
from scenario_registry import get_scenario_by_name


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id(scenario: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe = scenario.replace(" ", "_")
    return f"{ts}_{safe}"


@dataclass
class RunRequest:
    system: str
    project_root: Path
    scenario: Optional[str] = None
    profile: str = "smoke"
    mode: str = "vm"
    timeout_sec: int = 300
    retry: int = 0
    clean_save_slots: bool = True
    godot_bin: str = "godot4"
    scene: Optional[str] = None
    extra_args: list[str] = field(default_factory=list)
    dry_run: bool = False
    screenshot_prefix: Optional[str] = None
    enable_test_driver: bool = False
    flow_steps: list[dict] = field(default_factory=list)
    flow_step_timeout_sec: int = 15
    driver_ready_timeout_sec: int = 20
    driver_no_activity_timeout_sec: int = 5
    test_driver_session: Optional[str] = None
    user_data_dir: Optional[Path] = None
    reload_project_before_run: bool = False
    reload_timeout_sec: int = 20
    requested_run_id: Optional[str] = None
    step_prepare_pause_ms: int = 0
    step_verify_pause_ms: int = 0
    allow_parallel: bool = False

    def normalized_scenario(self) -> str:
        if self.scenario:
            return self.scenario
        return f"{self.system}_smoke"


@dataclass
class RunResult:
    run_id: str
    status: str
    exit_code: Optional[int]
    started_at: str
    finished_at: str
    artifact_root: str
    command: list[str]
    error: Optional[str] = None
    failure_category: Optional[str] = None
    failure_details: Optional[dict] = None

    def to_report(self, request: RunRequest, artifact_index: Optional[dict] = None) -> dict:
        flow_assertions = (self.failure_details or {}).get("flowAssertions", {})
        total_assertions = int(flow_assertions.get("total", 0))
        passed_assertions = int(flow_assertions.get("passed", 0))
        failed_assertions = int(flow_assertions.get("failed", 0))
        details = dict(self.failure_details or {})
        primary_failure = details.pop("primaryFailure", None)
        default_artifacts = [
            "logs/stdout.log",
            "logs/stderr.log",
            "run_meta.json",
        ] + self._visual_artifact_refs(artifact_index)
        failure_payload = {
            "stepId": "step_process_exec",
            "category": self.failure_category
            if self.failure_category
            else ("timeout" if self.status == "timeout" else "runtime_error"),
            "expected": "process exit code == 0",
            "actual": self.error or f"exit code {self.exit_code}",
            "details": details,
            "artifacts": default_artifacts,
        }
        if isinstance(primary_failure, dict):
            failure_payload["stepId"] = str(primary_failure.get("stepId", failure_payload["stepId"]))
            failure_payload["category"] = str(primary_failure.get("category", failure_payload["category"]))
            failure_payload["expected"] = str(primary_failure.get("expected", failure_payload["expected"]))
            failure_payload["actual"] = str(primary_failure.get("actual", failure_payload["actual"]))
            primary_artifacts = primary_failure.get("artifacts", [])
            if isinstance(primary_artifacts, list):
                merged = list(dict.fromkeys(primary_artifacts + default_artifacts))
                failure_payload["artifacts"] = merged
        result_status = "passed" if self.status == "finished" else "failed"
        process_exit_code = self.exit_code
        effective_exit_code = 0 if result_status == "passed" else self.exit_code
        failures = [] if self.status == "finished" else [failure_payload]
        primary_failure = failure_payload if failures else {}
        artifact_index = artifact_index or {}
        return {
            # v2 canonical fields
            "run_id": self.run_id,
            "result_status": result_status,
            "process_exit_code": process_exit_code,
            "effective_exit_code": effective_exit_code,
            "scenario": request.normalized_scenario(),
            "environment_v2": {"mode": request.mode, "godot_version": "unknown"},
            "summary_v2": {"total_assertions": total_assertions, "passed": passed_assertions, "failed": failed_assertions},
            "artifact_index": artifact_index,
            "primary_failure": {
                "step": str(primary_failure.get("stepId", "")),
                "step_id": str(primary_failure.get("stepId", "")),
                "category": str(primary_failure.get("category", "")),
                "expected": str(primary_failure.get("expected", "")),
                "actual": str(primary_failure.get("actual", "")),
                "artifacts": list(primary_failure.get("artifacts", []))
                if isinstance(primary_failure.get("artifacts", []), list)
                else [],
            },
            "failures": failures,
            # backward compatibility fields
            "runId": self.run_id,
            "status": result_status,
            "exitCode": effective_exit_code,
            "environment": {"mode": request.mode, "godotVersion": "unknown"},
            "summary": {"totalAssertions": total_assertions, "passed": passed_assertions, "failed": failed_assertions},
            "artifactIndex": artifact_index,
        }

    @staticmethod
    def _visual_artifact_refs(artifact_index: Optional[dict]) -> list[str]:
        if not artifact_index:
            return []
        copied = set(artifact_index.get("copiedScreenshots", []))
        refs: list[str] = []
        for name in (
            "screenshots/visual_ui_button_diff.png",
            "screenshots/visual_ui_button_diff_annotated.png",
        ):
            if name in copied:
                refs.append(name)
        return refs


class GameTestRunner:
    def __init__(self, project_root: Path, artifact_base: Optional[Path] = None) -> None:
        self.project_root = project_root.resolve()
        self.artifact_base = (
            artifact_base.resolve()
            if artifact_base
            else self.project_root / "artifacts" / "test-runs"
        )

    def _prepare_artifacts(self, run_id: str) -> Path:
        run_root = self.artifact_base / run_id
        (run_root / "screenshots").mkdir(parents=True, exist_ok=True)
        (run_root / "logs").mkdir(parents=True, exist_ok=True)
        (run_root / "save_snapshots").mkdir(parents=True, exist_ok=True)
        return run_root

    def _build_command(self, req: RunRequest, run_root: Path, test_driver_session: str) -> list[str]:
        scenario = req.normalized_scenario()
        scenario_def = get_scenario_by_name(scenario)
        scene = req.scene or (scenario_def.scene if scenario_def else None)
        cmd = [req.godot_bin, "--path", str(req.project_root)]
        user_data_dir = req.user_data_dir or (run_root / "user_data")
        cmd.extend(["--user-data-dir", str(user_data_dir)])
        if req.mode == "headless":
            cmd.append("--headless")
        if scene:
            cmd.append(scene)
        args = list(scenario_def.default_args) if scenario_def else []
        # Godot user args should be placed after `--`, otherwise `--flag` may be parsed as engine args.
        user_args = list(req.extra_args) if req.extra_args else (list(scenario_def.user_args) if scenario_def else [])
        if req.enable_test_driver and "--test-driver" not in user_args:
            user_args.append("--test-driver")
        if req.enable_test_driver:
            user_args.append(f"--test-driver-session={test_driver_session}")
        if user_args:
            args.append("--")
            args.extend(user_args)
        cmd.extend(args)
        return cmd

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_driver_flow_snapshot(self, run_root: Path, step_results: list[dict]) -> None:
        (run_root / "logs" / "driver_flow.json").write_text(
            json.dumps({"steps": step_results}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _append_driver_flow_event(self, run_root: Path, event: dict) -> None:
        logs_dir = run_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        path = logs_dir / "driver_flow_events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _write_final_meta(self, run_root: Path, meta: dict, result: RunResult) -> None:
        final_meta = dict(meta)
        final_meta["status"] = result.status
        final_meta["finishedAt"] = result.finished_at
        final_meta["exitCode"] = result.exit_code
        if result.error:
            final_meta["error"] = result.error
        self._write_json(run_root / "run_meta.json", final_meta)

    def _read_app_name(self) -> str:
        project_file = self.project_root / "project.godot"
        if not project_file.exists():
            return "GodotGame"
        text = project_file.read_text(encoding="utf-8")
        match = re.search(r'config/name="([^"]+)"', text)
        if not match:
            return "GodotGame"
        return match.group(1).strip() or "GodotGame"

    def _resolve_user_data_dir(self) -> Optional[Path]:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        app_name = self._read_app_name()
        return Path(appdata) / "Godot" / "app_userdata" / app_name

    def _copy_if_exists(self, src: Path, dst: Path) -> bool:
        if not src.exists() or not src.is_file():
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True

    @staticmethod
    def _unique_paths(paths: list[Optional[Path]]) -> list[Path]:
        out: list[Path] = []
        seen: set[str] = set()
        for p in paths:
            if p is None:
                continue
            key = str(p.resolve()) if p.exists() else str(p)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
        return out

    def _candidate_user_data_dirs(self, preferred: Optional[Path]) -> list[Path]:
        return self._unique_paths([preferred, self._resolve_user_data_dir()])

    def _select_artifact_user_data_dir(self, preferred: Optional[Path]) -> Optional[Path]:
        candidates = self._candidate_user_data_dirs(preferred)
        if not candidates:
            return None
        for candidate in candidates:
            if not candidate.exists():
                continue
            if (
                (candidate / "logs").exists()
                or (candidate / "test_screenshots").exists()
                or (candidate / "saves").exists()
            ):
                return candidate
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _collect_artifact_index(
        self,
        run_root: Path,
        screenshot_prefix: Optional[str] = None,
        user_data_dir: Optional[Path] = None,
    ) -> dict:
        logs_dir = run_root / "logs"
        screenshots_dir = run_root / "screenshots"
        save_dir = run_root / "save_snapshots"
        artifact_index: dict = {
            "artifactRoot": str(run_root),
            "logsDir": str(logs_dir),
            "screenshotsDir": str(screenshots_dir),
            "saveSnapshotsDir": str(save_dir),
            "copiedLogs": [],
            "copiedScreenshots": [],
            "saveFiles": [],
            "screenshotPrefixFilter": screenshot_prefix or "",
        }

        user_data_dir = self._select_artifact_user_data_dir(user_data_dir)
        if not user_data_dir:
            return artifact_index

        user_logs = user_data_dir / "logs"
        godot_log_src = user_logs / "godot.log"
        frame_log_src = user_logs / "debug_frame_overlay.txt"
        if self._copy_if_exists(godot_log_src, logs_dir / "godot.log"):
            artifact_index["copiedLogs"].append("logs/godot.log")
        if self._copy_if_exists(frame_log_src, logs_dir / "debug_frame_overlay.txt"):
            artifact_index["copiedLogs"].append("logs/debug_frame_overlay.txt")

        user_shots = user_data_dir / "test_screenshots"
        if user_shots.exists() and user_shots.is_dir():
            for shot in sorted(user_shots.glob("*.png")):
                if screenshot_prefix and not shot.name.startswith(screenshot_prefix):
                    continue
                dst = screenshots_dir / shot.name
                if self._copy_if_exists(shot, dst):
                    artifact_index["copiedScreenshots"].append(f"screenshots/{shot.name}")

        user_saves = user_data_dir / "saves"
        if user_saves.exists() and user_saves.is_dir():
            for item in sorted(user_saves.glob("*.save")):
                stat = item.stat()
                artifact_index["saveFiles"].append(
                    {
                        "name": item.name,
                        "size": stat.st_size,
                        "modifiedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    }
                )
        self._write_json(save_dir / "save_index.json", {"files": artifact_index["saveFiles"]})
        return artifact_index

    def _detect_failure_category(self, stdout_text: str, stderr_text: str, status: str) -> Optional[str]:
        if status == "timeout":
            return "timeout"
        haystack = (stdout_text + "\n" + stderr_text).lower()
        if "visual_regression" in haystack or "[visualregressionprobetest]" in haystack:
            return "visual_regression"
        return "runtime_error"

    def _extract_visual_details(self, stderr_text: str) -> dict:
        # Example: baseline mismatch diff=0.015719 threshold=0.002000
        match = re.search(r"diff=([0-9]*\.?[0-9]+)\s+threshold=([0-9]*\.?[0-9]+)", stderr_text)
        if not match:
            return {}
        diff_value = float(match.group(1))
        threshold_value = float(match.group(2))
        return {"diff": diff_value, "threshold": threshold_value}

    def _extract_runtime_errors(self, stdout_text: str, stderr_text: str) -> list[str]:
        findings: list[str] = []
        for line in (stdout_text + "\n" + stderr_text).splitlines():
            low = line.lower()
            if "script error" in low or "push_error" in low or low.startswith("error:"):
                findings.append(line.strip())
            if len(findings) >= 20:
                break
        return findings

    def _build_primary_failure(self, flow_failure: Optional[dict], fallback_error: str) -> Optional[dict]:
        if not isinstance(flow_failure, dict):
            return None
        step_id = str(flow_failure.get("stepId", "step_process_exec"))
        action = str(flow_failure.get("action", ""))
        code = str(flow_failure.get("errorCode", ""))
        message = str(flow_failure.get("errorMessage", "")).strip() or fallback_error
        check_kind = str(flow_failure.get("checkKind", ""))
        category = "driver_step_failed"
        expected = "driver step should return status ok"
        if action == "wait" and code == "TIMEOUT":
            category = "wait_timeout"
            expected = "wait condition should be satisfied within timeout"
        elif action == "click":
            expected = "target should be clickable and accepted by gameplay logic"
            if code == "TARGET_NOT_FOUND":
                category = "click_target_missing"
                expected = "target should exist in scene tree for this step"
            elif code == "TARGET_NOT_VISIBLE":
                category = "click_target_not_visible"
                expected = "target should be visible in tree when click executes"
            elif code == "TARGET_DISABLED":
                category = "click_target_disabled"
                expected = "target should be enabled before click"
            elif code == "ROOM_SELECTION_FAILED":
                category = "target_selection_not_confirmed"
                expected = "room click should enter cleanup/build confirm state"
            elif code == "UNSUPPORTED_TARGET":
                category = "click_unsupported_target"
                expected = "target type should support click injection"
            else:
                category = "click_injection_failed"
        elif action == "check":
            expected = "check expectation should match current game state"
            if code == "CHECK_FAILED":
                if check_kind == "logic_state" or "logic_state" in message:
                    category = "logic_state_mismatch"
                    expected = "logic state should converge to expected key/value"
                elif check_kind == "visual_hard" or "expected node visible" in message or "expected button disabled" in message:
                    category = "visual_hard_mismatch"
                    expected = "visual hard rule should match current UI state"
                else:
                    category = "assertion_failed"
            else:
                category = "assertion_failed"
        elif action == "setFault":
            category = "fault_injection_failed"
            expected = "fault marker should be configured before probe step"
        return {
            "stepId": step_id,
            "category": category,
            "expected": expected,
            "actual": f"{action} failed: {code} {message}".strip(),
            "artifacts": [
                "logs/driver_flow.json",
                "logs/godot.log",
                "logs/stderr.log",
            ],
        }

    def _reset_driver_ipc(self, user_data_dir: Optional[Path], session: str) -> None:
        if not session:
            return
        session_safe = re.sub(r"[^A-Za-z0-9._-]+", "_", session)
        for dir_candidate in self._candidate_user_data_dirs(user_data_dir):
            driver_dir = dir_candidate / "test_driver" / session_safe
            driver_dir.mkdir(parents=True, exist_ok=True)
            for file_name in ("command.json", "response.json"):
                file_path = driver_dir / file_name
                if file_path.exists() and file_path.is_file():
                    try:
                        file_path.unlink()
                    except OSError:
                        # Non-fatal: next handshake cycle can still recover.
                        pass

    def _write_junit_report(self, run_root: Path, req: RunRequest, result: RunResult) -> None:
        suite_name = req.normalized_scenario()
        case_name = f"{suite_name}.{req.profile}"
        is_ok = result.status == "finished"
        runtime_errors = (result.failure_details or {}).get("runtimeErrors", [])
        failure_xml = ""
        if not is_ok:
            failure_xml = (
                f'<failure message="{escape(result.error or "")}" '
                f'type="{escape(result.failure_category or "runtime_error")}">'
                f"{escape(json.dumps(result.failure_details or {}, ensure_ascii=False))}"
                "</failure>"
            )
        system_out = escape("\n".join(runtime_errors)) if runtime_errors else ""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<testsuite name="{escape(suite_name)}" tests="1" failures="{0 if is_ok else 1}" errors="0" skipped="0">'
            f'<testcase classname="{escape(suite_name)}" name="{escape(case_name)}" time="0">'
            f"{failure_xml}<system-out>{system_out}</system-out></testcase></testsuite>"
        )
        (run_root / "junit.xml").write_text(xml, encoding="utf-8")

    def _write_report_md(self, run_root: Path, req: RunRequest, result: RunResult, report_payload: dict) -> None:
        effective_exit_code = report_payload.get("effective_exit_code", 0 if result.status == "finished" else result.exit_code)
        process_exit_code = report_payload.get("process_exit_code", result.exit_code)
        lines = [
            "# Test Report",
            "",
            f"- run_id: `{result.run_id}`",
            f"- status: `{'passed' if result.status == 'finished' else 'failed'}`",
            f"- mode: `{req.mode}`",
            f"- effective_exit_code: `{effective_exit_code}`",
            f"- process_exit_code: `{process_exit_code}`",
            f"- error: `{result.error or ''}`",
        ]
        failures = report_payload.get("failures", [])
        f0 = failures[0] if failures else {}
        lines.extend(
            [
                "",
                "## Primary Failure",
                f"- step_id: `{str(f0.get('stepId', 'n/a'))}`",
                f"- category: `{str(f0.get('category', 'n/a'))}`",
                f"- expected: `{str(f0.get('expected', 'n/a'))}`",
                f"- actual: `{str(f0.get('actual', 'n/a'))}`",
            ]
        )
        artifacts = f0.get("artifacts", []) if isinstance(f0, dict) else []
        if isinstance(artifacts, list) and artifacts:
            lines.append("- artifacts:")
            for item in artifacts[:10]:
                lines.append(f"  - `{str(item)}`")
        (run_root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_failure_summary(self, run_root: Path, report_payload: dict) -> None:
        primary_failure = report_payload.get("primary_failure", {})
        if not isinstance(primary_failure, dict):
            primary_failure = {}
        key_files = [
            name
            for name in (
                "report.json",
                "report.md",
                "junit.xml",
                "flow_report.json",
                "logs/driver_flow.json",
            )
            if (run_root / name).exists()
        ]
        summary_payload = {
            "run_id": str(report_payload.get("run_id", report_payload.get("runId", ""))),
            "status": str(report_payload.get("status", "")),
            "result_status": str(report_payload.get("result_status", "")),
            "effective_exit_code": report_payload.get("effective_exit_code"),
            "process_exit_code": report_payload.get("process_exit_code"),
            "primary_failure": {
                "step": str(primary_failure.get("step", primary_failure.get("step_id", ""))),
                "category": str(primary_failure.get("category", "")),
                "expected": str(primary_failure.get("expected", "")),
                "actual": str(primary_failure.get("actual", "")),
                "artifacts": list(primary_failure.get("artifacts", []))
                if isinstance(primary_failure.get("artifacts", []), list)
                else [],
            },
            "key_files": key_files,
        }
        self._write_json(run_root / "failure_summary.json", summary_payload)

    def _reload_project(self, req: RunRequest, run_root: Path) -> Optional[str]:
        reload_cmd = [
            req.godot_bin,
            "--path",
            str(req.project_root),
            "--headless",
            "--quit",
        ]
        reload_stdout_path = run_root / "logs" / "reload_stdout.log"
        reload_stderr_path = run_root / "logs" / "reload_stderr.log"
        try:
            completed = subprocess.run(
                reload_cmd,
                cwd=str(req.project_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(3, int(req.reload_timeout_sec)),
                check=False,
            )
        except subprocess.TimeoutExpired:
            reload_stdout_path.write_text("", encoding="utf-8")
            reload_stderr_path.write_text(
                f"project reload timed out after {max(3, int(req.reload_timeout_sec))}s",
                encoding="utf-8",
            )
            return "project reload timeout"
        except FileNotFoundError as exc:
            reload_stdout_path.write_text("", encoding="utf-8")
            reload_stderr_path.write_text(str(exc), encoding="utf-8")
            return f"project reload executable not found: {exc}"
        except OSError as exc:
            reload_stdout_path.write_text("", encoding="utf-8")
            reload_stderr_path.write_text(str(exc), encoding="utf-8")
            return f"project reload os error: {exc}"

        reload_stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        reload_stderr_path.write_text(completed.stderr or "", encoding="utf-8")
        if completed.returncode != 0:
            return f"project reload failed with exit code {completed.returncode}"
        return None

    def run(self, req: RunRequest) -> RunResult:
        scenario = req.normalized_scenario()
        scenario_def = get_scenario_by_name(scenario)
        effective_screenshot_prefix = (
            req.screenshot_prefix
            if req.screenshot_prefix is not None
            else (scenario_def.screenshot_prefix if scenario_def else None)
        )
        run_id = str(req.requested_run_id or "").strip() or _run_id(scenario)
        run_root = self._prepare_artifacts(run_id)
        test_driver_session = req.test_driver_session or run_id
        effective_user_data_dir = req.user_data_dir or (run_root / "user_data")
        cmd = self._build_command(req, run_root=run_root, test_driver_session=test_driver_session)
        started_at = _utc_now_iso()

        meta = {
            "run_id": run_id,
            "status": "running",
            "system": req.system,
            "scenario": scenario,
            "profile": req.profile,
            "mode": req.mode,
            "timeoutSec": req.timeout_sec,
            "retry": req.retry,
            "projectRoot": str(req.project_root),
            "command": cmd,
            "startedAt": started_at,
            "dryRun": req.dry_run,
            "screenshotPrefix": effective_screenshot_prefix or "",
        }
        self._write_json(run_root / "run_meta.json", meta)

        if req.dry_run:
            result = RunResult(
                run_id=run_id,
                status="finished",
                exit_code=0,
                started_at=started_at,
                finished_at=_utc_now_iso(),
                artifact_root=str(run_root),
                command=cmd,
            )
            self._write_final_meta(run_root, meta, result)
            artifact_index = self._collect_artifact_index(
                run_root, effective_screenshot_prefix, user_data_dir=effective_user_data_dir
            )
            report_payload = result.to_report(req, artifact_index)
            self._write_json(run_root / "report.json", report_payload)
            self._write_junit_report(run_root, req, result)
            self._write_report_md(run_root, req, result, report_payload)
            self._write_failure_summary(run_root, report_payload)
            return result

        if req.reload_project_before_run:
            reload_error = self._reload_project(req, run_root)
            if reload_error:
                failed = RunResult(
                    run_id=run_id,
                    status="failed",
                    exit_code=None,
                    started_at=started_at,
                    finished_at=_utc_now_iso(),
                    artifact_root=str(run_root),
                    command=cmd,
                    error=reload_error,
                    failure_category="runtime_error",
                    failure_details={},
                )
                self._write_final_meta(run_root, meta, failed)
                artifact_index = self._collect_artifact_index(
                    run_root, effective_screenshot_prefix, user_data_dir=effective_user_data_dir
                )
                report_payload = failed.to_report(req, artifact_index)
                self._write_json(run_root / "report.json", report_payload)
                self._write_junit_report(run_root, req, failed)
                self._write_report_md(run_root, req, failed, report_payload)
                self._write_failure_summary(run_root, report_payload)
                return failed

        attempts = max(req.retry, 0) + 1
        last_result: Optional[RunResult] = None
        for attempt in range(1, attempts + 1):
            try:
                if req.enable_test_driver and req.flow_steps:
                    self._reset_driver_ipc(effective_user_data_dir, test_driver_session)
                stdout_path = run_root / "logs" / "stdout.log"
                stderr_path = run_root / "logs" / "stderr.log"
                with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_file, stderr_path.open(
                    "w", encoding="utf-8", errors="replace"
                ) as stderr_file:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=str(req.project_root),
                        stdout=stdout_file,
                        stderr=stderr_file,
                    )
                    lock_acquired = False
                    try:
                        acquire_runtime_lock(
                            project_root=req.project_root,
                            pid=int(proc.pid),
                            run_id=run_id,
                            owner="runner",
                            allow_parallel=bool(req.allow_parallel),
                        )
                        lock_acquired = True
                    except RuntimeError as exc:
                        proc.kill()
                        proc.wait(timeout=5)
                        err = str(exc)
                        last_result = RunResult(
                            run_id=run_id,
                            status="failed",
                            exit_code=None,
                            started_at=started_at,
                            finished_at=_utc_now_iso(),
                            artifact_root=str(run_root),
                            command=cmd,
                            error=f"test runtime already active: {err}",
                            failure_category="runtime_error",
                            failure_details={},
                        )
                        break

                    flow_assertions: dict = {"total": 0, "passed": 0, "failed": 0}
                    flow_error: Optional[str] = None
                    flow_failure: Optional[dict] = None
                    try:
                        if req.enable_test_driver and req.flow_steps:
                            flow_assertions, flow_error, flow_failure = self._execute_driver_flow(
                                req=req,
                                run_root=run_root,
                                expected_pid=proc.pid,
                                proc=proc,
                                user_data_dir=effective_user_data_dir,
                                session=test_driver_session,
                            )
                            if proc.poll() is None:
                                if flow_error:
                                    proc.kill()
                                else:
                                    # Flow is complete: end this dedicated test game process
                                    # immediately to avoid waiting for manual window close.
                                    proc.terminate()
                                    try:
                                        proc.wait(timeout=5)
                                    except subprocess.TimeoutExpired:
                                        proc.kill()
                        try:
                            proc.wait(timeout=req.timeout_sec)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)
                            last_result = RunResult(
                                run_id=run_id,
                                status="timeout",
                                exit_code=None,
                                started_at=started_at,
                                finished_at=_utc_now_iso(),
                                artifact_root=str(run_root),
                                command=cmd,
                                error=f"process timed out on attempt {attempt}",
                                failure_category="timeout",
                                failure_details={},
                            )
                            break
                    finally:
                        if lock_acquired:
                            release_runtime_lock(req.project_root, int(proc.pid))
                stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
                stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
                status = "finished" if proc.returncode == 0 and flow_error is None else "failed"
                if (
                    req.enable_test_driver
                    and req.flow_steps
                    and flow_error is None
                    and int(flow_assertions.get("total", 0)) > 0
                    and int(flow_assertions.get("failed", 0)) == 0
                ):
                    # In TestDriver mode we may terminate the game process right after
                    # the flow completes, which can produce a non-zero exit code.
                    # Flow assertions are the source of truth in this mode.
                    status = "finished"
                err = None if status == "finished" else f"non-zero exit code on attempt {attempt}"
                if flow_error:
                    err = flow_error
                category = None
                if status != "finished":
                    category = self._detect_failure_category(stdout_text or "", stderr_text or "", status)
                details: dict = {}
                runtime_errors = self._extract_runtime_errors(stdout_text or "", stderr_text or "")
                if runtime_errors:
                    details["runtimeErrors"] = runtime_errors
                primary_failure = self._build_primary_failure(flow_failure, err or "")
                if primary_failure:
                    details["primaryFailure"] = primary_failure
                if category == "visual_regression":
                    details = self._extract_visual_details(stderr_text or "")
                    if runtime_errors:
                        details["runtimeErrors"] = runtime_errors
                    if primary_failure:
                        details["primaryFailure"] = primary_failure
                    if details:
                        err = (
                            f"visual baseline mismatch diff={details['diff']:.6f} "
                            f"threshold={details['threshold']:.6f}"
                        )
                last_result = RunResult(
                    run_id=run_id,
                    status=status,
                    exit_code=proc.returncode,
                    started_at=started_at,
                    finished_at=_utc_now_iso(),
                    artifact_root=str(run_root),
                    command=cmd,
                    error=err,
                    failure_category=category,
                    failure_details={**details, "flowAssertions": flow_assertions},
                )
                if status == "finished":
                    break
            except FileNotFoundError as exc:
                (run_root / "logs" / "stdout.log").write_text("", encoding="utf-8")
                (run_root / "logs" / "stderr.log").write_text(str(exc), encoding="utf-8")
                last_result = RunResult(
                    run_id=run_id,
                    status="failed",
                    exit_code=None,
                    started_at=started_at,
                    finished_at=_utc_now_iso(),
                    artifact_root=str(run_root),
                    command=cmd,
                    error=f"executable not found on attempt {attempt}: {exc}",
                    failure_category="runtime_error",
                    failure_details={},
                )
                break
            except OSError as exc:
                (run_root / "logs" / "stdout.log").write_text("", encoding="utf-8")
                (run_root / "logs" / "stderr.log").write_text(str(exc), encoding="utf-8")
                last_result = RunResult(
                    run_id=run_id,
                    status="failed",
                    exit_code=None,
                    started_at=started_at,
                    finished_at=_utc_now_iso(),
                    artifact_root=str(run_root),
                    command=cmd,
                    error=f"os error on attempt {attempt}: {exc}",
                    failure_category="runtime_error",
                    failure_details={},
                )
                break

        assert last_result is not None
        self._write_final_meta(run_root, meta, last_result)
        artifact_index = self._collect_artifact_index(
            run_root, effective_screenshot_prefix, user_data_dir=effective_user_data_dir
        )
        report_payload = last_result.to_report(req, artifact_index)
        self._write_json(run_root / "report.json", report_payload)
        self._write_junit_report(run_root, req, last_result)
        self._write_report_md(run_root, req, last_result, report_payload)
        self._write_failure_summary(run_root, report_payload)
        return last_result

    def _execute_driver_flow(
        self,
        req: RunRequest,
        run_root: Path,
        expected_pid: Optional[int] = None,
        proc: Optional[subprocess.Popen] = None,
        user_data_dir: Optional[Path] = None,
        session: str = "",
    ) -> tuple[dict, Optional[str], Optional[dict]]:
        if not session:
            return {"total": 0, "passed": 0, "failed": 0}, "test driver session is required", None
        candidate_dirs = self._candidate_user_data_dirs(user_data_dir)
        if not candidate_dirs:
            return {"total": 0, "passed": 0, "failed": 0}, "test driver requires APPDATA user dir", None
        session_safe = re.sub(r"[^A-Za-z0-9._-]+", "_", session)
        driver_dirs: list[Path] = []
        for root in candidate_dirs:
            d = root / "test_driver" / session_safe
            d.mkdir(parents=True, exist_ok=True)
            driver_dirs.append(d)
        # Wait for driver ready file.
        ready_started = time.monotonic()
        ready_deadline = time.monotonic() + max(1.0, float(req.driver_ready_timeout_sec))
        active_client: Optional[DriverClient] = None
        while time.monotonic() <= ready_deadline:
            if proc is not None and proc.poll() is not None:
                return (
                    {"total": 0, "passed": 0, "failed": 0},
                    f"test driver process exited before ready (exit={proc.returncode})",
                    None,
                )
            if (
                req.driver_no_activity_timeout_sec > 0
                and all(not (d / "response.json").exists() for d in driver_dirs)
                and (time.monotonic() - ready_started) >= float(req.driver_no_activity_timeout_sec)
            ):
                if proc is not None and proc.poll() is None:
                    proc.kill()
                return (
                    {"total": 0, "passed": 0, "failed": 0},
                    (
                        "test driver no activity timeout after "
                        f"{int(req.driver_no_activity_timeout_sec)}s"
                    ),
                    None,
                )
            for d in driver_dirs:
                resp_file = d / "response.json"
                if not resp_file.exists():
                    continue
                try:
                    data = json.loads(resp_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if data.get("status") == "ready":
                    active_client = DriverClient(base_dir=d)
                    break
            if active_client is not None:
                break
            time.sleep(0.05)
        else:
            return {"total": 0, "passed": 0, "failed": 0}, "test driver did not become ready in time", None
        assert active_client is not None

        step_results: list[dict] = []
        passed = 0
        for idx, step in enumerate(req.flow_steps):
            step_id = str(step.get("id", ""))
            action = str(step.get("action", ""))
            params = dict(step.get("params", {}))
            timeout = float(step.get("timeoutSec", req.flow_step_timeout_sec))
            self._append_driver_flow_event(
                run_root,
                {
                    "type": "step_ready",
                    "ts": _utc_now_iso(),
                    "index": idx,
                    "step_id": step_id,
                    "action": action,
                },
            )
            if req.step_prepare_pause_ms > 0:
                time.sleep(max(0.0, float(req.step_prepare_pause_ms) / 1000.0))
            self._append_driver_flow_event(
                run_root,
                {
                    "type": "step_started",
                    "ts": _utc_now_iso(),
                    "index": idx,
                    "step_id": step_id,
                    "action": action,
                },
            )
            started = time.time()
            try:
                resp = active_client.send_and_wait(action=action, params=params, timeout_sec=timeout)
                ok = str(resp.get("status", "")) == "ok"
                if ok:
                    passed += 1
                step_results.append(
                    {
                        "step_id": step_id,
                        "action": action,
                        "status": "passed" if ok else "failed",
                        "response": resp,
                        "duration_ms": int((time.time() - started) * 1000),
                    }
                )
                self._write_driver_flow_snapshot(run_root, step_results)
                self._append_driver_flow_event(
                    run_root,
                    {
                        "type": "step_completed",
                        "ts": _utc_now_iso(),
                        "index": idx,
                        "step_id": step_id,
                        "action": action,
                        "status": "passed" if ok else "failed",
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                if not ok:
                    err_obj = resp.get("error", {}) if isinstance(resp.get("error", {}), dict) else {}
                    flow_failure = {
                        "stepId": step_id or "driver_step",
                        "action": action,
                        "errorCode": str(err_obj.get("code", "")),
                        "errorMessage": str(err_obj.get("message", "")),
                        "checkKind": str(params.get("kind", "")) if action == "check" else "",
                    }
                    return (
                        {"total": len(req.flow_steps), "passed": passed, "failed": len(req.flow_steps) - passed},
                        "driver step failed: %s" % action,
                        flow_failure,
                    )
                if req.step_verify_pause_ms > 0:
                    time.sleep(max(0.0, float(req.step_verify_pause_ms) / 1000.0))
            except Exception as exc:  # pylint: disable=broad-except
                step_results.append(
                    {
                        "step_id": step_id,
                        "action": action,
                        "status": "failed",
                        "error": str(exc),
                        "duration_ms": int((time.time() - started) * 1000),
                    }
                )
                self._write_driver_flow_snapshot(run_root, step_results)
                self._append_driver_flow_event(
                    run_root,
                    {
                        "type": "step_completed",
                        "ts": _utc_now_iso(),
                        "index": idx,
                        "step_id": step_id,
                        "action": action,
                        "status": "failed",
                        "duration_ms": int((time.time() - started) * 1000),
                        "error": str(exc),
                    },
                )
                flow_failure = {
                    "stepId": step_id or "driver_step",
                    "action": action,
                    "errorCode": "EXCEPTION",
                    "errorMessage": str(exc),
                    "checkKind": str(params.get("kind", "")) if action == "check" else "",
                }
                return (
                    {"total": len(req.flow_steps), "passed": passed, "failed": len(req.flow_steps) - passed},
                    "driver flow exception: %s" % exc,
                    flow_failure,
                )

        self._write_driver_flow_snapshot(run_root, step_results)
        return {"total": len(req.flow_steps), "passed": passed, "failed": len(req.flow_steps) - passed}, None, None
