#!/usr/bin/env python3
"""PointerGPF MCP server (CLI tool-style entry)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from basic_flow_contracts import build_dual_conclusions
from bug_fix_loop import run_bug_fix_loop
import remediation_handlers
from remediation_trace import RemediationTrace
from flow_execution import (
    FlowExecutionEngineStalled,
    FlowExecutionStepFailed,
    FlowExecutionTimeout,
    FlowRunOptions,
    FlowRunner,
)
from nl_intent_router import route_nl_intent
from repair_backend import build_l2_try_patch_from_env
from operational_profile import (
    build_operational_profile_bundle,
    pick_enter_game_candidate,
    split_flow_candidates_by_phase,
)


DEFAULT_SERVER_NAME = "pointer-gpf-mcp"
DEFAULT_SERVER_VERSION = "0.3.0.0"
DEFAULT_PLUGIN_ID = "pointer_gpf"
DEFAULT_PLUGIN_CFG_REL = f"addons/{DEFAULT_PLUGIN_ID}/plugin.cfg"
DEFAULT_RUNTIME_BRIDGE_AUTOLOAD_NAME = "PointerGPFRuntimeBridge"
DEFAULT_RUNTIME_BRIDGE_AUTOLOAD_PATH = f"*res://addons/{DEFAULT_PLUGIN_ID}/runtime_bridge.gd"
DEFAULT_WORKSPACE_DIR_REL = "pointer_gpf"
DEFAULT_CONTEXT_DIR_REL = f"{DEFAULT_WORKSPACE_DIR_REL}/project_context"
DEFAULT_SEED_FLOW_DIR_REL = f"{DEFAULT_WORKSPACE_DIR_REL}/generated_flows"
DEFAULT_REPORT_DIR_REL = f"{DEFAULT_WORKSPACE_DIR_REL}/reports"
DEFAULT_EXP_DIR_REL = f"{DEFAULT_WORKSPACE_DIR_REL}/gpf-exp"
DEFAULT_SCAN_ROOTS = ["scripts", "scenes", "addons", "datas", "docs", "flows", "tests", "test", "src"]


def _read_mcp_version_from_manifest(repo_root: Path) -> str | None:
    manifest = repo_root / "mcp" / "version_manifest.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        v = str(data.get("current_version", "")).strip()
        if v:
            return v
        ch = data.get("channels")
        if isinstance(ch, dict):
            st = ch.get("stable")
            if isinstance(st, dict):
                sv = str(st.get("version", "")).strip()
                if sv:
                    return sv
    return None


_MCP_IO_MODE = "header"
_STDIO_SOFT_ERROR_CAP = 8
_stdio_soft_errors = 0

_LEGACY_GAMEPLAYFLOW_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "check_test_runner_environment",
        "list_test_scenarios",
        "run_game_test",
        "get_test_artifacts",
        "get_test_report",
        "get_flow_timeline",
        "run_game_flow",
        "get_test_run_status",
        "cancel_test_run",
        "resume_fix_loop",
        "start_game_flow_live",
        "get_live_flow_progress",
        "run_and_stream_flow",
        "start_stepwise_flow",
        "prepare_step",
        "execute_step",
        "verify_step",
        "step_once",
        "run_stepwise_autopilot",
        "start_cursor_chat_plugin",
        "pull_cursor_chat_plugin",
    }
)


class AppError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass
class ServerCtx:
    repo_root: Path
    template_plugin_dir: Path


@dataclass
class RuntimeConfig:
    server_name: str
    server_version: str
    plugin_id: str
    plugin_cfg_rel: str
    context_dir_rel: str
    index_rel: str
    seed_flow_dir_rel: str
    report_dir_rel: str
    exp_dir_rel: str
    scan_roots: list[str]
    plugin_template_dir: Path
    config_sources: list[str]


@dataclass
class FileEntry:
    rel: str
    top: str
    suffix: str
    size: int
    mtime_ns: int

    def fingerprint(self) -> str:
        return f"{self.size}:{self.mtime_ns}"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_project_root(arguments: dict[str, Any]) -> Path:
    raw = str(arguments.get("project_root", "")).strip()
    if not raw:
        raise AppError("INVALID_ARGUMENT", "project_root is required")
    root = Path(raw).resolve()
    if not root.exists():
        raise AppError("INVALID_ARGUMENT", f"project_root not found: {root}")
    skip_godot_check = bool(arguments.get("skip_godot_project_check", False))
    if not skip_godot_check:
        pg = root / "project.godot"
        if not pg.is_file():
            raise AppError(
                "INVALID_GODOT_PROJECT",
                f"project.godot not found under project_root: {root}",
                {
                    "project_root": str(root),
                    "fix": "point project_root at a Godot project root directory, or pass skip_godot_project_check=true only for rare non-standard layouts",
                },
            )
    allow_temp_project = bool(arguments.get("allow_temp_project", False))
    if _is_path_under_temp_root(root) and not allow_temp_project:
        raise AppError(
            "TEMP_PROJECT_FORBIDDEN",
            "temp directory projects are not allowed by default",
            {
                "project_root": str(root),
                "fix": "use a non-temp project root, or set allow_temp_project=true only for isolated tests",
            },
        )
    return root


def _default_runtime_config(ctx: ServerCtx) -> RuntimeConfig:
    mv = _read_mcp_version_from_manifest(ctx.repo_root)
    ver = mv if mv else DEFAULT_SERVER_VERSION
    return RuntimeConfig(
        server_name=DEFAULT_SERVER_NAME,
        server_version=ver,
        plugin_id=DEFAULT_PLUGIN_ID,
        plugin_cfg_rel=DEFAULT_PLUGIN_CFG_REL,
        context_dir_rel=DEFAULT_CONTEXT_DIR_REL,
        index_rel=f"{DEFAULT_CONTEXT_DIR_REL}/index.json",
        seed_flow_dir_rel=DEFAULT_SEED_FLOW_DIR_REL,
        report_dir_rel=DEFAULT_REPORT_DIR_REL,
        exp_dir_rel=DEFAULT_EXP_DIR_REL,
        scan_roots=list(DEFAULT_SCAN_ROOTS),
        plugin_template_dir=ctx.template_plugin_dir,
        config_sources=[],
    )


def _merge_runtime_config(base: RuntimeConfig, payload: dict[str, Any], source_label: str) -> RuntimeConfig:
    cfg = RuntimeConfig(
        server_name=base.server_name,
        server_version=base.server_version,
        plugin_id=base.plugin_id,
        plugin_cfg_rel=base.plugin_cfg_rel,
        context_dir_rel=base.context_dir_rel,
        index_rel=base.index_rel,
        seed_flow_dir_rel=base.seed_flow_dir_rel,
        report_dir_rel=base.report_dir_rel,
        exp_dir_rel=base.exp_dir_rel,
        scan_roots=list(base.scan_roots),
        plugin_template_dir=base.plugin_template_dir,
        config_sources=list(base.config_sources),
    )
    if not isinstance(payload, dict):
        return cfg
    if payload.get("server_name"):
        cfg.server_name = str(payload.get("server_name")).strip()
    if payload.get("server_version"):
        cfg.server_version = str(payload.get("server_version")).strip()
    if payload.get("plugin_id"):
        cfg.plugin_id = str(payload.get("plugin_id")).strip()
    if payload.get("plugin_cfg_rel"):
        cfg.plugin_cfg_rel = str(payload.get("plugin_cfg_rel")).replace("\\", "/").strip()
    if payload.get("context_dir_rel"):
        cfg.context_dir_rel = str(payload.get("context_dir_rel")).replace("\\", "/").strip()
        cfg.index_rel = f"{cfg.context_dir_rel}/index.json"
    if payload.get("index_rel"):
        cfg.index_rel = str(payload.get("index_rel")).replace("\\", "/").strip()
    if payload.get("seed_flow_dir_rel"):
        cfg.seed_flow_dir_rel = str(payload.get("seed_flow_dir_rel")).replace("\\", "/").strip()
    if payload.get("report_dir_rel"):
        cfg.report_dir_rel = str(payload.get("report_dir_rel")).replace("\\", "/").strip()
    if payload.get("exp_dir_rel"):
        cfg.exp_dir_rel = str(payload.get("exp_dir_rel")).replace("\\", "/").strip()
    scan_roots = payload.get("scan_roots")
    if isinstance(scan_roots, list):
        normalized = [str(x).replace("\\", "/").strip() for x in scan_roots if str(x).strip()]
        if normalized:
            cfg.scan_roots = normalized
    tpl_rel = str(payload.get("plugin_template_dir_rel", "")).strip()
    if tpl_rel:
        cfg.plugin_template_dir = (base.plugin_template_dir.parents[2] / tpl_rel).resolve()
    if source_label not in cfg.config_sources:
        cfg.config_sources.append(source_label)
    return cfg


def _load_config_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AppError("CONFIG_READ_FAILED", f"failed to read config file: {path}", {"error": str(exc)}) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError("CONFIG_PARSE_FAILED", f"invalid json config file: {path}", {"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise AppError("CONFIG_INVALID", f"config file must be JSON object: {path}")
    return payload


def _resolve_runtime_config(ctx: ServerCtx, arguments: dict[str, Any], project_root: Path | None = None) -> RuntimeConfig:
    cfg = _default_runtime_config(ctx)
    repo_cfg = ctx.repo_root / "gtr.config.json"
    if repo_cfg.exists():
        cfg = _merge_runtime_config(cfg, _load_config_file(repo_cfg), str(repo_cfg))
    if project_root is None:
        project_root_raw = str(arguments.get("project_root", "")).strip()
        if project_root_raw:
            candidate = Path(project_root_raw).resolve()
            if candidate.exists():
                project_root = candidate
    if project_root is not None:
        project_cfg = project_root / "gtr.config.json"
        if project_cfg.exists():
            cfg = _merge_runtime_config(cfg, _load_config_file(project_cfg), str(project_cfg))
    config_file_raw = str(arguments.get("config_file", "")).strip()
    if config_file_raw:
        explicit_cfg = Path(config_file_raw).resolve()
        if not explicit_cfg.exists():
            raise AppError("CONFIG_NOT_FOUND", f"config_file not found: {explicit_cfg}")
        cfg = _merge_runtime_config(cfg, _load_config_file(explicit_cfg), str(explicit_cfg))
    return cfg


def _safe_read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _write_text(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise AppError("IO_ERROR", f"failed to write file: {path}", {"error": str(exc)}) from exc


def _append_text(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:
        raise AppError("IO_ERROR", f"failed to append file: {path}", {"error": str(exc)}) from exc


def _exp_runtime_dir(project_root: Path, cfg: RuntimeConfig) -> Path:
    return (project_root / cfg.exp_dir_rel / "runtime").resolve()


def _probe_runtime_gate(project_root: Path) -> dict[str, Any]:
    """Detect runtime mode hints for flow execution gate.

    This keeps compatibility with file-bridge workflows by allowing a lightweight
    marker file in `pointer_gpf/tmp/runtime_gate.json`.
    """
    bridge_dir = (project_root / "pointer_gpf" / "tmp").resolve()
    marker = bridge_dir / "runtime_gate.json"
    default = {
        "runtime_mode": "editor_bridge",
        "runtime_entry": "unknown",
        "runtime_gate_passed": False,
        "input_mode": "in_engine_virtual_input",
        "os_input_interference": False,
    }
    if not marker.exists() or not marker.is_file():
        return default
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(payload, dict):
        return default
    runtime_mode = str(payload.get("runtime_mode", "editor_bridge")).strip() or "editor_bridge"
    runtime_entry = str(payload.get("runtime_entry", "unknown")).strip() or "unknown"
    gate_passed = bool(payload.get("runtime_gate_passed", runtime_mode == "play_mode"))
    return {
        "runtime_mode": runtime_mode,
        "runtime_entry": runtime_entry,
        "runtime_gate_passed": gate_passed,
        "input_mode": "in_engine_virtual_input",
        "os_input_interference": False,
    }


def _request_auto_enter_play_mode(project_root: Path) -> bool:
    bridge_dir = (project_root / "pointer_gpf" / "tmp").resolve()
    request_file = bridge_dir / "auto_enter_play_mode.flag"
    try:
        bridge_dir.mkdir(parents=True, exist_ok=True)
        request_file.write_text(_utc_iso(), encoding="utf-8")
        return True
    except OSError:
        return False


def _await_runtime_gate(project_root: Path, *, timeout_ms: int = 8_000, poll_ms: int = 120) -> dict[str, Any]:
    timeout_ms = max(1, int(timeout_ms))
    poll_ms = max(10, int(poll_ms))
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    latest = _probe_runtime_gate(project_root)
    while time.monotonic() < deadline:
        latest = _probe_runtime_gate(project_root)
        if bool(latest.get("runtime_gate_passed", False)):
            return latest
        time.sleep(poll_ms / 1000.0)
    return latest


def _load_godot_executable_from_project_config(project_root: Path) -> str:
    cfg_path = (project_root / "tools" / "game-test-runner" / "config" / "godot_executable.json").resolve()
    if not cfg_path.exists() or not cfg_path.is_file():
        return ""
    try:
        payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in ("godot_executable", "godot_bin", "GODOT_BIN"):
        val = str(payload.get(key, "")).strip()
        if val:
            return val
    return ""


def _discover_godot_executable_candidates(arguments: dict[str, Any], project_root: Path) -> list[str]:
    candidates: list[str] = []
    cfg_exe = _load_godot_executable_from_project_config(project_root)
    if cfg_exe:
        candidates.append(cfg_exe)
    for key in ("godot_executable", "godot_editor_executable", "godot_path"):
        raw = str(arguments.get(key, "")).strip()
        if raw:
            candidates.append(raw)
    for env_key in ("GODOT_EXE", "GODOT_EDITOR_PATH", "GODOT_PATH"):
        raw = str(os.environ.get(env_key, "")).strip()
        if raw:
            candidates.append(raw)
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        key = raw.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(raw.strip())
    return deduped


def _is_godot_editor_running_for_project(project_root: Path) -> bool:
    project_text = str(project_root)
    if os.name == "nt":
        escaped = project_text.replace("'", "''")
        command = (
            "$p = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
            "Where-Object { $_.Name -like 'Godot*.exe' -and $_.CommandLine -match '--editor' "
            f"-and $_.CommandLine -match [regex]::Escape('{escaped}') }} | "
            "Select-Object -First 1 -ExpandProperty ProcessId; "
            "if ($p) { Write-Output $p }"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                check=False,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return bool(proc.stdout.strip())
    try:
        proc = subprocess.run(
            ["pgrep", "-af", "godot"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if not proc.stdout.strip():
        return False
    target = project_text.lower()
    for line in proc.stdout.splitlines():
        low = line.lower()
        if "--editor" in low and target in low:
            return True
    return False


def _launch_godot_editor(project_root: Path, executable: str) -> tuple[bool, str, int]:
    exe = Path(executable.strip()).expanduser()
    if not exe.exists() or not exe.is_file():
        return False, f"executable_not_found:{executable}", -1
    cmd = [str(exe), "--editor", "--path", str(project_root)]
    try:
        if os.name == "nt":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            proc = subprocess.Popen(
                cmd,
                cwd=str(project_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        else:
            proc = subprocess.Popen(
                cmd,
                cwd=str(project_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        return True, "", int(getattr(proc, "pid", -1) or -1)
    except OSError as exc:
        return False, str(exc), -1


def _is_path_under_temp_root(path: Path) -> bool:
    try:
        temp_root = Path(tempfile.gettempdir()).resolve()
        target = path.resolve()
        return temp_root == target or temp_root in target.parents
    except OSError:
        return False


def _ensure_runtime_play_mode(project_root: Path, arguments: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime_meta = _probe_runtime_gate(project_root)
    bootstrap: dict[str, Any] = {
        "target_project_root": str(project_root),
        "initial_runtime_mode": runtime_meta.get("runtime_mode", "editor_bridge"),
        "initial_runtime_gate_passed": bool(runtime_meta.get("runtime_gate_passed", False)),
        "auto_enter_play_mode_requested": False,
        "editor_running_before_launch": False,
        "launch_attempted": False,
        "launch_succeeded": False,
        "selected_executable": "",
        "launch_process_id": -1,
        "launched_executable": "",
        "launch_error": "",
        "candidate_count": 0,
    }
    if bool(runtime_meta.get("runtime_gate_passed", False)):
        return runtime_meta, bootstrap

    bootstrap["auto_enter_play_mode_requested"] = _request_auto_enter_play_mode(project_root)
    runtime_meta = _await_runtime_gate(project_root, timeout_ms=2_500, poll_ms=120)
    if bool(runtime_meta.get("runtime_gate_passed", False)):
        return runtime_meta, bootstrap

    bootstrap["editor_running_before_launch"] = _is_godot_editor_running_for_project(project_root)
    candidates = _discover_godot_executable_candidates(arguments, project_root)
    bootstrap["candidate_count"] = len(candidates)
    disable_autostart = bool(arguments.get("disable_engine_autostart", False))
    bootstrap["engine_autostart_disabled"] = disable_autostart
    launch_allowed = not disable_autostart
    if launch_allowed and _is_path_under_temp_root(project_root):
        launch_allowed = False
        bootstrap["launch_block_reason"] = "temp_project_autostart_blocked"
    if not bootstrap["editor_running_before_launch"] and launch_allowed:
        for exe in candidates:
            bootstrap["launch_attempted"] = True
            bootstrap["selected_executable"] = exe
            ok, err, pid = _launch_godot_editor(project_root, exe)
            if ok:
                bootstrap["launch_succeeded"] = True
                bootstrap["launched_executable"] = exe
                bootstrap["launch_process_id"] = pid
                break
            if not bootstrap["launch_error"]:
                bootstrap["launch_error"] = err
    if launch_allowed and not bootstrap["editor_running_before_launch"] and not candidates:
        bootstrap["launch_error"] = "no_executable_candidates"
    base_post_ms = 18_000 if bootstrap["launch_succeeded"] or bootstrap["editor_running_before_launch"] else 1_500
    agent_session = _agent_session_defaults_requested(arguments)
    post_wait_ms = int(max(base_post_ms, 24_000 if agent_session else base_post_ms))
    _request_auto_enter_play_mode(project_root)
    runtime_meta = _await_runtime_gate(project_root, timeout_ms=post_wait_ms, poll_ms=120)
    return runtime_meta, bootstrap


def _request_project_close(project_root: Path, *, timeout_ms: int = 1_500) -> dict[str, Any]:
    bridge_dir = (project_root / "pointer_gpf" / "tmp").resolve()
    cmd_path = bridge_dir / "command.json"
    rsp_path = bridge_dir / "response.json"
    run_id = f"close_{uuid.uuid4().hex}"
    seq = 9_000_001
    payload: dict[str, Any] = {
        "schema": "pointer_gpf.flow_command.v1",
        "run_id": run_id,
        "seq": seq,
        "action": "closeProject",
        "step": {"id": "close_project_session", "action": "closeProject"},
    }
    try:
        bridge_dir.mkdir(parents=True, exist_ok=True)
        if rsp_path.exists():
            try:
                rsp_path.unlink()
            except OSError:
                pass
        cmd_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        return {
            "requested": False,
            "acknowledged": False,
            "timeout_ms": timeout_ms,
            "reason": f"io_error:{exc}",
        }

    deadline = time.monotonic() + max(1, int(timeout_ms)) / 1000.0
    while time.monotonic() < deadline:
        if rsp_path.is_file():
            try:
                rsp = json.loads(rsp_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(0.03)
                continue
            if not isinstance(rsp, dict):
                time.sleep(0.03)
                continue
            if str(rsp.get("run_id", "")) != run_id:
                time.sleep(0.03)
                continue
            try:
                rsp_seq = int(rsp.get("seq", -1))
            except (TypeError, ValueError):
                time.sleep(0.03)
                continue
            if rsp_seq != seq:
                time.sleep(0.03)
                continue
            return {
                "requested": True,
                "acknowledged": bool(rsp.get("ok", False)),
                "timeout_ms": timeout_ms,
                "message": str(rsp.get("message", "")),
            }
        time.sleep(0.03)
    return {
        "requested": True,
        "acknowledged": False,
        "timeout_ms": timeout_ms,
        "reason": "close_response_timeout_or_process_exited",
    }


def _project_close_skipped_meta() -> dict[str, Any]:
    return {
        "requested": False,
        "acknowledged": False,
        "timeout_ms": 0,
        "reason": "preserve_engine_open",
    }


def _maybe_request_project_close(project_root: Path, close_project_on_finish: bool) -> dict[str, Any]:
    if not close_project_on_finish:
        return _project_close_skipped_meta()
    return _request_project_close(project_root)


def _windows_find_godot_pids_holding_path(project_root: Path) -> list[int]:
    """Return PIDs whose command line mentions Godot and contains the project path (Windows / PowerShell)."""
    norm = str(project_root.resolve()).replace("\\", "/").lower()
    norm_esc = norm.replace("'", "''")
    ps_script = (
        f"$pn = '{norm_esc}'; "
        "Get-CimInstance Win32_Process | Where-Object { "
        "  $cl = $_.CommandLine; "
        "  $cl -and "
        "  (($cl.Replace([char]92,'/').ToLowerInvariant()) -match 'godot') -and "
        "  ($cl.Replace([char]92,'/').ToLowerInvariant().Contains($pn)) "
        "} | ForEach-Object { [int]$_.ProcessId }"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        creationflags=creationflags,
    )
    if proc.returncode != 0:
        raise OSError(f"powershell list processes failed: {proc.stderr.strip() or proc.stdout.strip()}")
    out: list[int] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(int(line))
        except ValueError:
            continue
    return sorted(set(out))


def _posix_find_godot_pids_holding_path(project_root: Path) -> list[int]:
    norm = str(project_root.resolve()).lower()
    # Linux: ps -eo pid= args= ; macOS often supports ps -ax -o pid=,command=
    for ps_args in (["ps", "-eo", "pid=", "-o", "args="], ["ps", "-ax", "-o", "pid=", "-o", "command="]):
        proc = subprocess.run(ps_args, capture_output=True, text=True, timeout=25, check=False)
        if proc.returncode != 0:
            continue
        pids: list[int] = []
        for raw in proc.stdout.splitlines():
            line = raw.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            blob = parts[1].lower()
            if "godot" not in blob:
                continue
            blob_slash = blob.replace("\\", "/")
            if norm.replace("\\", "/") in blob_slash or norm in blob:
                pids.append(pid)
        return sorted(set(pids))
    raise OSError("failed to enumerate processes via ps")


def _force_terminate_godot_processes_holding_project(project_root: Path) -> dict[str, Any]:
    """Best-effort: kill processes that look like Godot and reference project_root. Caller must opt in."""
    try:
        if os.name == "nt":
            pids = _windows_find_godot_pids_holding_path(project_root)
        else:
            pids = _posix_find_godot_pids_holding_path(project_root)
    except OSError as exc:
        return {"outcome": "enumerate_failed", "pids": [], "detail": str(exc)}
    if not pids:
        return {
            "outcome": "no_matching_process",
            "pids": [],
            "detail": f"no Godot process with command line containing {project_root}",
        }
    killed: list[int] = []
    errors: list[str] = []
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for pid in pids:
        try:
            if os.name == "nt":
                proc = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                    creationflags=creationflags,
                )
                if proc.returncode != 0:
                    errors.append(f"pid {pid}: {proc.stderr.strip() or proc.stdout.strip()}")
                else:
                    killed.append(pid)
            else:
                os.kill(pid, signal.SIGTERM)
                killed.append(pid)
        except OSError as exc:
            errors.append(f"pid {pid}: {exc}")
    return {
        "outcome": "terminated" if killed else "terminate_failed",
        "pids": killed,
        "detail": "; ".join(errors) if errors else "",
    }


def _hard_teardown_for_flow_failure(
    project_root: Path,
    arguments: dict[str, Any],
    close_meta: dict[str, Any],
) -> dict[str, Any]:
    """Structured evidence after a failed flow: whether Play likely still runs, and optional process kill."""
    requested = bool(close_meta.get("requested", False))
    acknowledged = bool(close_meta.get("acknowledged", False))
    force = bool(arguments.get("force_terminate_godot_on_flow_failure", False))
    block: dict[str, Any] = {
        "close_requested": requested,
        "close_acknowledged": acknowledged,
        "user_must_check_engine_process": requested and not acknowledged,
        "force_terminate_godot": {
            "opt_in": force,
            "attempted": False,
            "outcome": "",
            "pids": [],
            "detail": "",
        },
    }
    ft = block["force_terminate_godot"]
    if not requested:
        ft["outcome"] = "close_not_requested"
        ft["detail"] = "close_project_on_finish was false; no bridge close was sent"
        return block
    if acknowledged:
        ft["outcome"] = "skipped_close_acknowledged"
        ft["detail"] = "closeProject was acknowledged; engine should be back in editor idle"
        return block
    if not force:
        ft["outcome"] = "disabled_by_default"
        ft["detail"] = (
            "closeProject was not acknowledged within timeout; Play mode may still be running. "
            "Pass force_terminate_godot_on_flow_failure=true only if you accept terminating Godot processes "
            "whose command line contains this project_root (may close the editor holding the project)."
        )
        return block
    ft["attempted"] = True
    res = _force_terminate_godot_processes_holding_project(project_root)
    ft["outcome"] = str(res.get("outcome", ""))
    ft["pids"] = list(res.get("pids", []))
    ft["detail"] = str(res.get("detail", ""))
    return block


def _attach_hard_teardown(
    details: dict[str, Any],
    project_root: Path,
    arguments: dict[str, Any],
    close_meta: dict[str, Any],
) -> None:
    details["hard_teardown"] = _hard_teardown_for_flow_failure(project_root, arguments, close_meta)


def _issue_text_from_flow_app_error(exc: AppError) -> str:
    det = exc.details if isinstance(exc.details, dict) else {}
    sug = det.get("auto_fix_arguments_suggestion")
    if isinstance(sug, dict):
        iss = str(sug.get("issue", "")).strip()
        if iss:
            return iss
    return f"{exc.code}: {exc.message}"


def _issue_text_from_execution_payload(payload: dict[str, Any]) -> str:
    rep = payload.get("execution_report")
    if not isinstance(rep, dict):
        rep = payload
    status = str(rep.get("status", "")).strip()
    rid = str(rep.get("run_id", "")).strip()
    return f"basic flow finished with status={status!r} run_id={rid!r}"


def _env_auto_repair_default() -> bool:
    raw = os.environ.get("GPF_AUTO_REPAIR_DEFAULT")
    if raw is None:
        return True
    return raw.strip() not in ("0", "false", "False", "")


def _truthy_env(name: str) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return False
    return raw.strip() in ("1", "true", "True", "yes", "YES")


def _agent_session_defaults_requested(arguments: dict[str, Any]) -> bool:
    if bool(arguments.get("agent_session_defaults")):
        return True
    return _truthy_env("GPF_AGENT_SESSION_DEFAULTS")


_NON_REPAIRABLE_FLOW_APP_CODES = frozenset(
    {
        "INVALID_ARGUMENT",
        "TEMP_PROJECT_FORBIDDEN",
        "INVALID_GODOT_PROJECT",
        "BROADCAST_ENTRY_REQUIRED",
    }
)


def _parse_auto_repair_params(arguments: dict[str, Any]) -> tuple[bool, int, int]:
    if "auto_repair" in arguments:
        auto_repair = bool(arguments.get("auto_repair"))
    elif _agent_session_defaults_requested(arguments):
        auto_repair = True
    else:
        auto_repair = _env_auto_repair_default()
    raw_mr = arguments.get("max_repair_rounds", 2)
    try:
        max_repair_rounds = int(raw_mr) if raw_mr is not None else 2
    except (TypeError, ValueError):
        max_repair_rounds = 2
    max_repair_rounds = max(1, min(8, max_repair_rounds))
    raw_fc = arguments.get("auto_fix_max_cycles", 3)
    try:
        fix_cycles = int(raw_fc) if raw_fc is not None else 3
    except (TypeError, ValueError):
        fix_cycles = 3
    fix_cycles = max(0, fix_cycles)
    return auto_repair, max_repair_rounds, fix_cycles


def _invoke_auto_fix_round_for_flow(
    ctx: ServerCtx,
    fix_base: dict[str, Any],
    issue: str,
    fix_cycles: int,
) -> dict[str, Any]:
    if fix_cycles <= 0:
        return {"skipped": True, "reason": "auto_fix_max_cycles=0"}
    try:
        payload = _tool_auto_fix_game_bug(
            ctx,
            {
                **fix_base,
                "issue": issue,
                "max_cycles": fix_cycles,
                "auto_repair": False,
            },
        )
        return {"ok": True, "result": payload}
    except AppError as fix_exc:
        return {"ok": False, "error": fix_exc.as_dict()}


def _remediation_class_for_app_error(exc: AppError) -> str:
    from failure_taxonomy import FailureSignal, classify_failure

    raw = str(exc.code or "").strip()
    return classify_failure(FailureSignal(raw if raw else None, None, None))


def _remediation_class_for_execution_bundle(payload: dict[str, Any]) -> str:
    from failure_taxonomy import FailureSignal, classify_failure

    ae = payload.get("app_error")
    code: str | None = None
    if isinstance(ae, dict):
        c = ae.get("code")
        if c is not None and str(c).strip():
            code = str(c)
    rep = payload.get("execution_report")
    step: str | None = None
    if isinstance(rep, dict):
        st = str(rep.get("status", "")).strip().lower()
        if st:
            step = st
        ae2 = rep.get("app_error")
        if isinstance(ae2, dict) and ae2.get("code"):
            code = str(ae2["code"])
    if step is None:
        st2 = str(payload.get("status", "")).strip().lower()
        step = st2 if st2 else None
    return classify_failure(FailureSignal(code, step, None))


def _auto_repair_round_for_flow_exception(
    ctx: ServerCtx,
    fix_base: dict[str, Any],
    project_root: Path,
    exc: AppError,
    issue: str,
    auto_fix_max_cycles: int,
) -> dict[str, Any]:
    rc = _remediation_class_for_app_error(exc)
    details = exc.details if isinstance(exc.details, dict) else {}
    hr = remediation_handlers.run_handlers(rc, ctx, project_root, fix_base, details)
    entry: dict[str, Any] = {
        "remediation_class": rc,
        "remediation_handler": hr,
        "issue_used_for_auto_fix": issue,
    }
    if hr.get("handled"):
        entry["auto_fix"] = {"skipped": True, "reason": "remediation_handler_handled"}
    else:
        entry["auto_fix"] = _invoke_auto_fix_round_for_flow(ctx, fix_base, issue, auto_fix_max_cycles)
    return entry


def _auto_repair_round_for_flow_failed_payload(
    ctx: ServerCtx,
    fix_base: dict[str, Any],
    project_root: Path,
    payload: dict[str, Any],
    issue: str,
    auto_fix_max_cycles: int,
) -> dict[str, Any]:
    rc = _remediation_class_for_execution_bundle(payload)
    hr = remediation_handlers.run_handlers(rc, ctx, project_root, fix_base, payload)
    entry: dict[str, Any] = {
        "remediation_class": rc,
        "remediation_handler": hr,
        "issue_used_for_auto_fix": issue,
    }
    if hr.get("handled"):
        entry["auto_fix"] = {"skipped": True, "reason": "remediation_handler_handled"}
    else:
        entry["auto_fix"] = _invoke_auto_fix_round_for_flow(ctx, fix_base, issue, auto_fix_max_cycles)
    return entry


def _merge_remediation_traces_from_rounds(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in rounds:
        af = entry.get("auto_fix")
        if not isinstance(af, dict):
            continue
        res = af.get("result")
        if isinstance(res, dict):
            rt = res.get("remediation_trace")
            if isinstance(rt, dict):
                out.append(rt)
    return out


def _legacy_layout_hints(project_root: Path) -> list[dict[str, str]]:
    candidates = [
        ("gameplayflow/project_context", "legacy_project_context"),
        ("gameplayflow/generated_flows", "legacy_generated_flows"),
        ("gpf-exp", "legacy_exp_root"),
    ]
    out: list[dict[str, str]] = []
    for rel, kind in candidates:
        p = project_root / rel
        if p.exists():
            out.append(
                {
                    "kind": kind,
                    "path": str(p),
                    "message": f"legacy path detected: {rel}. Run scripts/migrate-legacy-layout.ps1 to migrate into pointer_gpf/",
                }
            )
    return out


def _write_exp_runtime_artifact(
    project_root: Path,
    cfg: RuntimeConfig,
    artifact_name: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    runtime_dir = _exp_runtime_dir(project_root, cfg)
    slug = _slugify(artifact_name) or "runtime_artifact"
    artifact_path = runtime_dir / f"{slug}.json"
    _write_text(artifact_path, json.dumps(payload, ensure_ascii=False, indent=2))
    event_path = runtime_dir / "events.ndjson"
    _append_text(event_path, json.dumps(payload, ensure_ascii=False) + "\n")
    return {
        "exp_output_dir": str((project_root / cfg.exp_dir_rel).resolve()),
        "exp_runtime_dir": str(runtime_dir),
        "artifact_file": str(artifact_path),
        "event_log_file": str(event_path),
    }


def _resolve_existing_file(raw: str, field_name: str) -> Path:
    path = Path(str(raw).strip()).resolve()
    if not str(raw).strip():
        raise AppError("INVALID_ARGUMENT", f"{field_name} is required")
    if not path.exists() or not path.is_file():
        raise AppError("INVALID_ARGUMENT", f"{field_name} not found: {path}")
    return path


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError("INVALID_ARGUMENT", f"invalid json file: {path}", {"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise AppError("INVALID_ARGUMENT", f"json file must contain object: {path}")
    return payload


def _is_png_file(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(8) == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False


def _convert_image_to_png_if_needed(source: Path, target_png: Path) -> Path:
    if _is_png_file(source):
        if source.resolve() != target_png.resolve():
            shutil.copyfile(source, target_png)
        return target_png
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pylint: disable=broad-except
        raise AppError(
            "INVALID_ARGUMENT",
            "figma_screenshot_file is not a valid PNG; install Pillow or provide PNG input",
            {"file": str(source), "error": str(exc)},
        ) from exc
    try:
        img = Image.open(source)
        img.save(target_png, format="PNG")
    except Exception as exc:  # pylint: disable=broad-except
        raise AppError("INVALID_ARGUMENT", "failed to convert baseline image to PNG", {"error": str(exc)}) from exc
    return target_png


def _byte_diff_ratio(left: bytes, right: bytes) -> float:
    if not left and not right:
        return 0.0
    max_len = max(len(left), len(right))
    total = abs(len(left) - len(right)) * 255
    common = min(len(left), len(right))
    for idx in range(common):
        total += abs(left[idx] - right[idx])
    return round(total / (max_len * 255), 6)


def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_png_scanlines(payload: bytes, width: int, height: int, bytes_per_pixel: int) -> bytes:
    stride = width * bytes_per_pixel
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        if pos >= len(payload):
            break
        filter_type = payload[pos]
        pos += 1
        if pos + stride > len(payload):
            break
        row = bytearray(payload[pos : pos + stride])
        pos += stride
        if filter_type == 1:
            for i in range(stride):
                left = row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                row[i] = (row[i] + left) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                up = prev[i]
                row[i] = (row[i] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                left = row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                up = prev[i]
                up_left = prev[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                row[i] = (row[i] + _paeth_predictor(left, up, up_left)) & 0xFF
        out.extend(row)
        prev = row
    return bytes(out)


def _parse_png_metrics(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    signature = b"\x89PNG\r\n\x1a\n"
    if len(raw) < 8 or raw[:8] != signature:
        return {"format": "unknown", "width": 0, "height": 0, "raw_payload": b"", "byte_size": len(raw)}
    offset = 8
    width = 0
    height = 0
    bit_depth = 0
    color_type = 0
    idat_parts: list[bytes] = []
    while offset + 8 <= len(raw):
        chunk_len = struct.unpack(">I", raw[offset : offset + 4])[0]
        chunk_type = raw[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + chunk_len
        crc_end = data_end + 4
        if crc_end > len(raw):
            break
        chunk_data = raw[data_start:data_end]
        if chunk_type == b"IHDR" and len(chunk_data) >= 13:
            width = struct.unpack(">I", chunk_data[0:4])[0]
            height = struct.unpack(">I", chunk_data[4:8])[0]
            bit_depth = int(chunk_data[8])
            color_type = int(chunk_data[9])
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            break
        offset = crc_end
    decompressed = b""
    if idat_parts:
        try:
            decompressed = zlib.decompress(b"".join(idat_parts))
        except zlib.error:
            decompressed = b""
    pixel_data = b""
    channels_map = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    channels = channels_map.get(color_type, 0)
    if decompressed and width > 0 and height > 0 and bit_depth == 8 and channels > 0:
        pixel_data = _unfilter_png_scanlines(decompressed, width, height, channels)
    return {
        "format": "png",
        "width": width,
        "height": height,
        "raw_payload": decompressed,
        "pixel_data": pixel_data,
        "byte_size": len(raw),
        "bit_depth": bit_depth,
        "color_type": color_type,
    }


def _extract_figma_layout_expectation(design_context: dict[str, Any]) -> dict[str, Any]:
    frame = design_context.get("frame")
    if isinstance(frame, dict):
        width = int(frame.get("width", 0) or 0)
        height = int(frame.get("height", 0) or 0)
        return {"width": width, "height": height}
    return {"width": 0, "height": 0}


def _resolve_project_file(project_root: Path, raw: str, default_rel: str) -> Path:
    value = str(raw).strip()
    if not value:
        return (project_root / default_rel).resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (project_root / value).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def _parse_texture_rect_nodes(scene_file: Path) -> list[dict[str, Any]]:
    text = _safe_read_text(scene_file)
    if not text:
        return []
    out: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[node "):
            if current and {"name", "top", "bottom", "left", "right"} <= set(current.keys()):
                out.append(current)
            match = re.search(r'name="([^"]+)"\s+type="([^"]+)"', stripped)
            if match and match.group(2) == "TextureRect":
                current = {"name": match.group(1)}
            else:
                current = None
            continue
        if current is None:
            continue
        if stripped.startswith("offset_left ="):
            current["left"] = float(stripped.split("=", 1)[1].strip())
        elif stripped.startswith("offset_top ="):
            current["top"] = float(stripped.split("=", 1)[1].strip())
        elif stripped.startswith("offset_right ="):
            current["right"] = float(stripped.split("=", 1)[1].strip())
        elif stripped.startswith("offset_bottom ="):
            current["bottom"] = float(stripped.split("=", 1)[1].strip())
    if current and {"name", "top", "bottom", "left", "right"} <= set(current.keys()):
        out.append(current)
    return out


def _build_uniform_height_plan(
    scene_file: Path,
    target_height: float,
    node_name_pattern: str,
) -> dict[str, Any]:
    nodes = _parse_texture_rect_nodes(scene_file)
    if target_height <= 0 or not nodes:
        return {"target_height": target_height, "matched_nodes": [], "adjustments": []}
    pattern = re.compile(node_name_pattern) if node_name_pattern else re.compile(r".*")
    adjustments: list[dict[str, Any]] = []
    for node in nodes:
        name = str(node.get("name", ""))
        if not pattern.search(name):
            continue
        old_w = float(node["right"]) - float(node["left"])
        old_h = float(node["bottom"]) - float(node["top"])
        if old_h <= 0:
            continue
        scale = target_height / old_h
        new_w = round(old_w * scale, 3)
        new_h = round(target_height, 3)
        new_right = round(float(node["left"]) + new_w, 3)
        new_bottom = round(float(node["top"]) + new_h, 3)
        adjustments.append(
            {
                "node": name,
                "old_size": {"width": round(old_w, 3), "height": round(old_h, 3)},
                "new_size": {"width": new_w, "height": new_h},
                "scale_factor": round(scale, 6),
                "patch_hint": {
                    "offset_right": new_right,
                    "offset_bottom": new_bottom,
                },
            }
        )
    matched = [a["node"] for a in adjustments]
    return {
        "target_height": round(target_height, 3),
        "matched_nodes": matched,
        "adjustments": adjustments,
    }


def _resolve_compare_report_payload(compare_report_file: Path) -> tuple[dict[str, Any], Path]:
    payload = _read_json_file(compare_report_file)
    if isinstance(payload.get("visual_diff"), dict) and str(payload.get("run_id", "")).strip():
        return payload, compare_report_file
    report_ref = str(payload.get("report_file", "")).strip()
    if report_ref:
        resolved = _resolve_existing_file(report_ref, "report_file")
        full = _read_json_file(resolved)
        if isinstance(full.get("visual_diff"), dict) and str(full.get("run_id", "")).strip():
            return full, resolved
    return payload, compare_report_file


def _compute_resized_diff_ratio(figma_file: Path, game_file: Path, expected_w: int, expected_h: int) -> tuple[float, dict[str, Any]]:
    info: dict[str, Any] = {"resized_for_compare": False, "method": "raw_payload"}
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return 1.0, info
    try:
        figma_img = Image.open(figma_file).convert("RGB")
        game_img = Image.open(game_file).convert("RGB")
        if figma_img.size != (expected_w, expected_h):
            figma_img = figma_img.resize((expected_w, expected_h))
            info["resized_for_compare"] = True
        if game_img.size != (expected_w, expected_h):
            game_img = game_img.resize((expected_w, expected_h))
            info["resized_for_compare"] = True
        info["method"] = "pillow_rgb"
        return _byte_diff_ratio(figma_img.tobytes(), game_img.tobytes()), info
    except Exception as exc:  # pylint: disable=broad-except
        info["error"] = str(exc)
        return 1.0, info


def _ensure_plugin_enabled(project_root: Path, plugin_cfg_rel: str) -> dict[str, Any]:
    project_cfg = project_root / "project.godot"
    if not project_cfg.exists():
        raise AppError("PROJECT_GODOT_NOT_FOUND", f"missing file: {project_cfg}")
    text = _safe_read_text(project_cfg)
    target = f"res://{plugin_cfg_rel}"
    if "[editor_plugins]" not in text:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n[editor_plugins]\n"
        text += f'enabled=PackedStringArray("{target}")\n'
        _write_text(project_cfg, text)
        return {"enabled": True, "mode": "section_created"}
    lines = text.splitlines()
    section_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == "[editor_plugins]":
            section_idx = i
            break
    if section_idx < 0:
        raise AppError("INTERNAL_ERROR", "failed to locate [editor_plugins] section")
    key_idx = -1
    for i in range(section_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            break
        if stripped.startswith("enabled="):
            key_idx = i
            break
    if key_idx < 0:
        lines.insert(section_idx + 1, f'enabled=PackedStringArray("{target}")')
        _write_text(project_cfg, "\n".join(lines) + "\n")
        return {"enabled": True, "mode": "key_created"}
    current_line = lines[key_idx]
    if target in current_line:
        return {"enabled": True, "mode": "already_enabled"}
    prefix = "enabled=PackedStringArray("
    if current_line.strip().startswith(prefix) and current_line.strip().endswith(")"):
        inside = current_line.strip()[len(prefix) : -1].strip()
        new_inside = f'{inside}, "{target}"' if inside else f'"{target}"'
        lines[key_idx] = f"{prefix}{new_inside})"
    else:
        lines[key_idx] = f'enabled=PackedStringArray("{target}")'
    _write_text(project_cfg, "\n".join(lines) + "\n")
    return {"enabled": True, "mode": "key_updated"}


def _ensure_runtime_bridge_autoload(
    project_root: Path,
    autoload_name: str = DEFAULT_RUNTIME_BRIDGE_AUTOLOAD_NAME,
    autoload_path: str = DEFAULT_RUNTIME_BRIDGE_AUTOLOAD_PATH,
) -> dict[str, Any]:
    project_cfg = project_root / "project.godot"
    if not project_cfg.exists():
        raise AppError("PROJECT_GODOT_NOT_FOUND", f"missing file: {project_cfg}")
    text = _safe_read_text(project_cfg)
    if "[autoload]" not in text:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n[autoload]\n"
        text += f'{autoload_name}="{autoload_path}"\n'
        _write_text(project_cfg, text)
        return {"enabled": True, "mode": "section_created"}
    lines = text.splitlines()
    section_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == "[autoload]":
            section_idx = i
            break
    if section_idx < 0:
        raise AppError("INTERNAL_ERROR", "failed to locate [autoload] section")
    key_idx = -1
    for i in range(section_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            break
        if stripped.startswith(f"{autoload_name}="):
            key_idx = i
            break
    desired = f'{autoload_name}="{autoload_path}"'
    if key_idx < 0:
        lines.insert(section_idx + 1, desired)
        _write_text(project_cfg, "\n".join(lines) + "\n")
        return {"enabled": True, "mode": "key_created"}
    if lines[key_idx].strip() == desired:
        return {"enabled": True, "mode": "already_enabled"}
    lines[key_idx] = desired
    _write_text(project_cfg, "\n".join(lines) + "\n")
    return {"enabled": True, "mode": "key_updated"}


def _tool_install_godot_plugin(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    if not cfg.plugin_template_dir.exists():
        raise AppError("PLUGIN_TEMPLATE_NOT_FOUND", f"missing template dir: {cfg.plugin_template_dir}")
    target_dir = project_root / "addons" / cfg.plugin_id
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(cfg.plugin_template_dir, target_dir)
    enable_result = _ensure_plugin_enabled(project_root, cfg.plugin_cfg_rel)
    autoload_result = _ensure_runtime_bridge_autoload(project_root)
    report = {
        "tool": "install_godot_plugin",
        "generated_at": _utc_iso(),
        "project_root": str(project_root),
        "plugin_target_dir": str(target_dir),
        "plugin_cfg": f"res://{cfg.plugin_cfg_rel}",
        "config_sources": cfg.config_sources,
        "enable_result": enable_result,
        "autoload_result": autoload_result,
        "status": "installed",
    }
    report_path = project_root / cfg.report_dir_rel / "plugin_install_report.json"
    _write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    report["report_path"] = str(report_path)
    return report


def _tool_enable_godot_plugin(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    plugin_cfg = project_root / cfg.plugin_cfg_rel
    if not plugin_cfg.exists():
        raise AppError(
            "PLUGIN_NOT_INSTALLED",
            "plugin files not found, run install_godot_plugin first",
            {"expected_plugin_cfg": str(plugin_cfg)},
        )
    enable_result = _ensure_plugin_enabled(project_root, cfg.plugin_cfg_rel)
    autoload_result = _ensure_runtime_bridge_autoload(project_root)
    return {
        "tool": "enable_godot_plugin",
        "generated_at": _utc_iso(),
        "project_root": str(project_root),
        "plugin_cfg": f"res://{cfg.plugin_cfg_rel}",
        "config_sources": cfg.config_sources,
        "enable_result": enable_result,
        "autoload_result": autoload_result,
        "status": "enabled",
    }


def _tool_update_godot_plugin(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    result = _tool_install_godot_plugin(ctx, arguments)
    result["tool"] = "update_godot_plugin"
    result["status"] = "updated"
    return result


def _tool_check_plugin_status(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    project_cfg = project_root / "project.godot"
    plugin_cfg = project_root / cfg.plugin_cfg_rel
    enabled = False
    if project_cfg.exists():
        content = _safe_read_text(project_cfg)
        enabled = f"res://{cfg.plugin_cfg_rel}" in content
    return {
        "project_root": str(project_root),
        "plugin_cfg_exists": plugin_cfg.exists(),
        "plugin_enabled_in_project_godot": enabled,
        "plugin_cfg": f"res://{cfg.plugin_cfg_rel}",
        "config_sources": cfg.config_sources,
        "status": "ready" if plugin_cfg.exists() and enabled else "not_ready",
    }


def _scan_files(project_root: Path, scan_roots: list[str], limit: int = 2500) -> list[FileEntry]:
    allow_roots = scan_roots or list(DEFAULT_SCAN_ROOTS)
    seen: set[str] = set()
    out: list[FileEntry] = []
    for root_name in allow_roots:
        base = project_root / root_name
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(project_root)).replace("\\", "/")
            if rel in seen:
                continue
            st = path.stat()
            out.append(
                FileEntry(
                    rel=rel,
                    top=rel.split("/", 1)[0],
                    suffix=path.suffix.lower(),
                    size=int(st.st_size),
                    mtime_ns=int(st.st_mtime_ns),
                )
            )
            seen.add(rel)
            if len(out) >= limit:
                return out
    for rel_name in ("project.godot", "README.md", "README.txt"):
        p = project_root / rel_name
        if not p.exists() or not p.is_file():
            continue
        rel = str(p.relative_to(project_root)).replace("\\", "/")
        if rel in seen:
            continue
        st = p.stat()
        out.append(
            FileEntry(
                rel=rel,
                top=rel.split("/", 1)[0],
                suffix=p.suffix.lower(),
                size=int(st.st_size),
                mtime_ns=int(st.st_mtime_ns),
            )
        )
    return sorted(out, key=lambda x: x.rel)


def _extract_project_name(project_root: Path) -> str:
    raw = _safe_read_text(project_root / "project.godot")
    match = re.search(r'config/name\s*=\s*"([^"]+)"', raw)
    return match.group(1).strip() if match else ""


def _extract_script_signals(project_root: Path, files: list[FileEntry], max_items: int = 50) -> dict[str, Any]:
    scripts = [f for f in files if f.suffix == ".gd"]
    classes: list[str] = []
    extends: list[str] = []
    methods: list[str] = []
    for entry in scripts[:200]:
        text = _safe_read_text(project_root / entry.rel)
        for c in re.findall(r"^\s*class_name\s+([A-Za-z0-9_]+)", text, flags=re.MULTILINE):
            if c not in classes:
                classes.append(c)
        for e in re.findall(r"^\s*extends\s+([A-Za-z0-9_\.]+)", text, flags=re.MULTILINE):
            if e not in extends:
                extends.append(e)
        for m in re.findall(r"^\s*func\s+([A-Za-z0-9_]+)\s*\(", text, flags=re.MULTILINE):
            if m not in methods:
                methods.append(m)
    return {
        "script_count": len(scripts),
        "class_names": classes[:max_items],
        "extends_types": extends[:max_items],
        "method_samples": methods[:max_items],
    }


def _extract_scene_signals(project_root: Path, files: list[FileEntry], max_items: int = 50) -> dict[str, Any]:
    scenes = [f for f in files if f.suffix == ".tscn"]
    roots: list[dict[str, str]] = []
    named_nodes: list[dict[str, str]] = []
    button_nodes: list[dict[str, str]] = []
    control_nodes: list[dict[str, str]] = []
    for entry in scenes[:200]:
        text = _safe_read_text(project_root / entry.rel)
        match = re.search(r'^\[node\s+name="([^"]+)"\s+type="([^"]+)"', text, flags=re.MULTILINE)
        if match:
            roots.append({"scene": entry.rel, "root_name": match.group(1), "root_type": match.group(2)})
        for node_match in re.finditer(
            r'^\[node\s+name="([^"]+)"\s+type="([^"]+)"(?:\s+parent="([^"]+)")?',
            text,
            flags=re.MULTILINE,
        ):
            node_name = node_match.group(1)
            node_type = node_match.group(2)
            parent = (node_match.group(3) or ".").strip()
            node_path = node_name if parent in {"", "."} else f"{parent}/{node_name}"
            node_info = {"scene": entry.rel, "name": node_name, "type": node_type, "path": node_path}
            named_nodes.append(node_info)
            if node_type in {"Button", "TextureButton", "CheckButton", "OptionButton", "MenuButton", "LinkButton"}:
                button_nodes.append(node_info)
            if node_type in {"Control", "Panel", "CanvasLayer"} or node_type.endswith("Container"):
                control_nodes.append(node_info)
        if len(roots) >= max_items:
            break
    return {
        "scene_count": len(scenes),
        "root_nodes": roots,
        "named_nodes": named_nodes[: max_items * 10],
        "button_nodes": button_nodes[: max_items * 10],
        "control_nodes": control_nodes[: max_items * 10],
    }


def _extract_data_signals(project_root: Path, files: list[FileEntry], max_files: int = 40) -> dict[str, Any]:
    json_files = [f for f in files if f.suffix == ".json" and f.top in {"datas", "data", "config"}]
    top_keys: dict[str, int] = {}
    parsed_files = 0
    for entry in json_files[:max_files]:
        raw = _safe_read_text(project_root / entry.rel)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        parsed_files += 1
        if isinstance(payload, dict):
            for key in payload.keys():
                skey = str(key)
                top_keys[skey] = top_keys.get(skey, 0) + 1
    ranked = sorted(top_keys.items(), key=lambda x: (-x[1], x[0]))
    return {
        "json_file_count": len(json_files),
        "json_parsed_count": parsed_files,
        "top_keys": [{"key": k, "freq": v} for k, v in ranked[:80]],
    }


def _derive_flow_candidates(
    script_signals: dict[str, Any],
    scene_signals: dict[str, Any],
    data_signals: dict[str, Any],
    inferred_keywords: list[str],
) -> dict[str, Any]:
    methods = [str(x) for x in script_signals.get("method_samples", []) if isinstance(x, str)]
    root_nodes = [x for x in scene_signals.get("root_nodes", []) if isinstance(x, dict)]
    button_nodes = [x for x in scene_signals.get("button_nodes", []) if isinstance(x, dict)]
    control_nodes = [x for x in scene_signals.get("control_nodes", []) if isinstance(x, dict)]
    data_keys = [str(x.get("key")) for x in data_signals.get("top_keys", []) if isinstance(x, dict)]

    actions: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    action_ids: set[str] = set()
    assertion_ids: set[str] = set()

    def push_action(
        action_id: str,
        kind: str,
        hint: str,
        evidence: list[str],
        target_hint: str = "",
        until_hint: str = "",
    ) -> None:
        if action_id in action_ids:
            return
        action_ids.add(action_id)
        payload: dict[str, Any] = {"id": action_id, "kind": kind, "hint": hint, "evidence": evidence[:5]}
        if target_hint.strip():
            payload["target_hint"] = target_hint.strip()
        if until_hint.strip():
            payload["until_hint"] = until_hint.strip()
        actions.append(payload)

    def push_assert(
        assert_id: str,
        kind: str,
        hint: str,
        evidence: list[str],
        target_hint: str = "",
    ) -> None:
        if assert_id in assertion_ids:
            return
        assertion_ids.add(assert_id)
        payload: dict[str, Any] = {"id": assert_id, "kind": kind, "hint": hint, "evidence": evidence[:5]}
        if target_hint.strip():
            payload["target_hint"] = target_hint.strip()
        assertions.append(payload)

    for button in button_nodes[:120]:
        node_name = str(button.get("name", "")).strip()
        scene = str(button.get("scene", "")).strip()
        if not node_name:
            continue
        push_action(
            f"action.click.node.{node_name}",
            "click",
            f"点击按钮 `{node_name}`，验证可交互路径",
            [f"scene_button:{scene}:{node_name}"],
            target_hint=f"node_name:{node_name}",
        )

    for method in methods:
        low = method.lower()
        if "pressed" in low or low.startswith("_on_"):
            target_hint = ""
            match = re.match(r"^_on_([a-z0-9_]+)_pressed$", low)
            if match:
                token = match.group(1).strip("_")
                if token:
                    target_hint = f"name_token:{token}"
            push_action(
                f"action.click.{method}",
                "click",
                f"尝试通过按钮/交互信号触发 `{method}` 对应路径",
                [f"method:{method}"],
                target_hint=target_hint,
            )
        if low.startswith("is_") or low.startswith("has_") or low.startswith("can_"):
            push_assert(
                f"assert.logic.{method}",
                "logic_state",
                f"把 `{method}` 映射为状态断言",
                [f"method:{method}"],
            )
        if "state" in low or "status" in low:
            push_assert(
                f"assert.state.{method}",
                "logic_state",
                f"优先检查 `{method}` 对应状态变化",
                [f"method:{method}"],
            )

    for root in root_nodes[:40]:
        scene = str(root.get("scene", ""))
        rname = str(root.get("root_name", ""))
        rtype = str(root.get("root_type", ""))
        if "Control" in rtype or "Panel" in rtype:
            push_action(
                f"action.open_ui.{rname}",
                "click",
                f"进入 `{scene}` 后验证 UI 根节点 `{rname}` 可见/可交互",
                [f"scene:{scene}", f"root:{rname}", f"type:{rtype}"],
                target_hint=f"node_name:{rname}",
            )
            push_assert(
                f"assert.ui.visible.{rname}",
                "visual_hard",
                f"检查 `{rname}` 的可见性与布局稳定性",
                [f"scene:{scene}", f"type:{rtype}"],
            )
        if "Node2D" in rtype or "Node3D" in rtype:
            push_action(
                f"action.enter_scene.{rname}",
                "wait",
                f"进入 `{scene}` 后等待 `{rname}` 场景树稳定",
                [f"scene:{scene}", f"type:{rtype}"],
                until_hint=f"node_exists:{rname}",
            )

    for control in control_nodes[:120]:
        cname = str(control.get("name", "")).strip()
        cpath = str(control.get("path", "")).strip()
        scene = str(control.get("scene", "")).strip()
        if not cname:
            continue
        # Prefer top-level controls for stable runtime assertions.
        if cpath and "/" in cpath:
            continue
        push_assert(
            f"assert.logic.visible.{cname}",
            "logic_state",
            f"校验控件 `{cname}` 在关键步骤后可见性状态",
            [f"scene_control:{scene}:{cpath or cname}"],
            target_hint=f"node_visible:{cname}",
        )

    for key in data_keys[:40]:
        low = key.lower()
        if any(x in low for x in ("resource", "currency", "value", "stats", "factor")):
            push_assert(
                f"assert.data.{key}",
                "logic_state",
                f"构造资源/数值断言，重点跟踪 `{key}`",
                [f"data_key:{key}"],
            )
        if any(x in low for x in ("room", "map", "region", "explore")):
            push_action(
                f"action.progress.{key}",
                "wait",
                f"围绕 `{key}` 构造推进与解锁流程",
                [f"data_key:{key}"],
                until_hint=f"data_hint:{key}",
            )

    if "ui-heavy" in inferred_keywords:
        push_assert(
            "assert.ui.snapshot.baseline",
            "visual_hard",
            "该项目偏 UI 驱动，建议默认启用截图/布局基线断言",
            ["keyword:ui-heavy"],
        )
    if "exploration" in inferred_keywords:
        push_action(
            "action.explore.region_cycle",
            "wait",
            "检测到探索关键词，建议加入 region/map 轮转流程",
            ["keyword:exploration"],
            until_hint="keyword:exploration",
        )
    if "builder" in inferred_keywords:
        push_action(
            "action.builder.build_cycle",
            "wait",
            "检测到建造关键词，建议覆盖 build->wait->verify 完整闭环",
            ["keyword:builder"],
            until_hint="keyword:builder",
        )

    return {
        "action_candidates": actions[:120],
        "assertion_candidates": assertions[:120],
    }


def _flow_candidates_markdown(flow_candidates: dict[str, Any]) -> str:
    actions = [x for x in flow_candidates.get("action_candidates", []) if isinstance(x, dict)]
    assertions = [x for x in flow_candidates.get("assertion_candidates", []) if isinstance(x, dict)]
    parts: list[str] = [
        "# Flow Candidate Catalog",
        "",
        "## Action Candidates",
        "",
    ]
    if actions:
        parts.extend(
            [
                f"- `{item.get('id')}` ({item.get('kind')}): {item.get('hint')}"
                for item in actions[:80]
                if isinstance(item.get("id"), str)
            ]
        )
    else:
        parts.append("- none")
    parts.extend(["", "## Assertion Candidates", ""])
    if assertions:
        parts.extend(
            [
                f"- `{item.get('id')}` ({item.get('kind')}): {item.get('hint')}"
                for item in assertions[:80]
                if isinstance(item.get("id"), str)
            ]
        )
    else:
        parts.append("- none")
    return "\n".join(parts) + "\n"


def _extract_todo_signals(project_root: Path, files: list[FileEntry], max_items: int = 80) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    markers = ("TODO", "FIXME", "待办", "待處理", "待处理")
    for entry in files:
        if entry.suffix not in (".md", ".gd", ".json", ".txt", ".tscn", ".cfg", ".py"):
            continue
        text = _safe_read_text(project_root / entry.rel)
        if not text:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            if any(marker in line for marker in markers):
                hits.append({"file": entry.rel, "line": idx, "text": line.strip()[:220]})
                if len(hits) >= max_items:
                    return hits
    return hits


def _infer_keywords(files: list[FileEntry]) -> list[str]:
    corpus = " ".join(entry.rel.lower() for entry in files)
    mapping = {
        "rpg": ("battle", "quest", "inventory", "skill"),
        "builder": ("build", "construction", "room", "base"),
        "exploration": ("explore", "region", "map", "investigation"),
        "simulation": ("sim", "tick", "economy", "resource"),
        "ui-heavy": ("ui", "panel", "overlay", "layout"),
    }
    out: list[str] = []
    for key, words in mapping.items():
        if any(w in corpus for w in words):
            out.append(key)
    return out


def _context_unknowns(project_root: Path) -> list[str]:
    missing: list[str] = []
    if not (project_root / "project.godot").exists():
        missing.append("project.godot missing; runtime contract unknown")
    if not (project_root / "scenes").exists():
        missing.append("scenes/ not found; scene entrypoints unknown")
    if not (project_root / "scripts").exists():
        missing.append("scripts/ not found; gameplay logic modules unknown")
    if not (project_root / "flows").exists():
        missing.append("flows/ not found; flow templates unavailable")
    return missing


def _confidence_score(files: list[FileEntry], unknowns: list[str]) -> float:
    score = 0.3
    tops = {f.top for f in files}
    if "project.godot" in {f.rel for f in files}:
        score += 0.2
    if "scripts" in tops:
        score += 0.2
    if "scenes" in tops:
        score += 0.15
    if "datas" in tops or "data" in tops:
        score += 0.1
    if "docs" in tops:
        score += 0.05
    score -= min(0.25, 0.05 * len(unknowns))
    return round(max(0.05, min(0.99, score)), 2)


def _load_previous_index(project_root: Path, index_rel: str) -> dict[str, Any]:
    path = project_root / index_rel
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_context_index_or_fail(project_root: Path, index_rel: str) -> dict[str, Any]:
    path = project_root / index_rel
    if not path.exists():
        raise AppError(
            "CONTEXT_INDEX_NOT_FOUND",
            "missing project context index; run init_project_context first",
            {"expected_index": str(path)},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError("CONTEXT_INDEX_INVALID", "failed to parse context index", {"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise AppError("CONTEXT_INDEX_INVALID", "context index must be a JSON object")
    return payload


def _slugify(text: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_]+", "_", str(text).strip())
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw.lower() or "flow_seed"


def _compute_delta(previous: dict[str, Any], files: list[FileEntry]) -> dict[str, Any]:
    prev_map = previous.get("file_fingerprints", {}) if isinstance(previous.get("file_fingerprints"), dict) else {}
    current_map = {f.rel: f.fingerprint() for f in files}
    prev_keys = set(prev_map.keys())
    cur_keys = set(current_map.keys())
    added = sorted(cur_keys - prev_keys)
    removed = sorted(prev_keys - cur_keys)
    changed = sorted([k for k in (cur_keys & prev_keys) if str(prev_map.get(k)) != str(current_map.get(k))])
    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added_samples": added[:25],
        "removed_samples": removed[:25],
        "changed_samples": changed[:25],
        "has_delta": bool(added or removed or changed),
    }


def _interaction_static_rank(action: dict[str, Any]) -> int:
    si = action.get("static_interaction") if isinstance(action.get("static_interaction"), dict) else {}
    lk = str(si.get("player_click_likelihood", "medium"))
    return {"high": 3, "medium": 2, "low": 1, "none": 0}.get(lk, 2)


def _rank_click_actions_by_static_interaction(
    actions: list[dict[str, Any]],
    *,
    allow_low_likelihood: bool = False,
) -> list[dict[str, Any]]:
    sorted_a = sorted(actions, key=lambda x: -_interaction_static_rank(x))
    if allow_low_likelihood:
        return sorted_a
    non_none = [x for x in sorted_a if _interaction_static_rank(x) > 0]
    return non_none if non_none else sorted_a


def _enrich_flow_candidates_static_interaction(
    project_root: Path,
    flow_candidates: dict[str, Any],
    viewport: tuple[int, int],
) -> None:
    from scene_interaction_model import parse_tscn_nodes, summarize_control_interaction

    cache: dict[str, list[Any]] = {}
    for act in flow_candidates.get("action_candidates", []):
        if not isinstance(act, dict):
            continue
        for ev in act.get("evidence", []) or []:
            if not isinstance(ev, str) or not ev.startswith("scene_button:"):
                continue
            rest = ev[len("scene_button:") :]
            idx = rest.rfind(":")
            if idx <= 0:
                continue
            scene_rel = rest[:idx].replace("\\", "/")
            node_name = rest[idx + 1 :]
            if scene_rel not in cache:
                p = project_root / scene_rel
                if p.is_file():
                    cache[scene_rel] = parse_tscn_nodes(p.read_text(encoding="utf-8", errors="replace"))
                else:
                    cache[scene_rel] = []
            nodes = cache[scene_rel]
            if nodes:
                act["static_interaction"] = summarize_control_interaction(nodes, node_name, viewport=viewport)
            break


def _build_context_docs(
    project_root: Path,
    files: list[FileEntry],
    previous: dict[str, Any],
    cfg: RuntimeConfig,
) -> dict[str, Any]:
    generated_at = _utc_iso()
    context_dir = project_root / cfg.context_dir_rel
    by_prefix: dict[str, int] = {}
    by_suffix: dict[str, int] = {}
    for rel in files:
        by_prefix[rel.top] = by_prefix.get(rel.top, 0) + 1
        by_suffix[rel.suffix or "<none>"] = by_suffix.get(rel.suffix or "<none>", 0) + 1
    unknowns = _context_unknowns(project_root)
    confidence = _confidence_score(files, unknowns)
    project_name = _extract_project_name(project_root) or "(unknown)"
    script_signals = _extract_script_signals(project_root, files)
    scene_signals = _extract_scene_signals(project_root, files)
    data_signals = _extract_data_signals(project_root, files)
    todo_signals = _extract_todo_signals(project_root, files)
    keywords = _infer_keywords(files)
    flow_candidates = _derive_flow_candidates(
        script_signals=script_signals,
        scene_signals=scene_signals,
        data_signals=data_signals,
        inferred_keywords=keywords,
    )
    from scene_interaction_model import read_viewport_size_from_project

    _enrich_flow_candidates_static_interaction(
        project_root,
        flow_candidates,
        read_viewport_size_from_project(project_root / "project.godot"),
    )
    delta = _compute_delta(previous, files)

    overview = (
        "# Project Overview\n\n"
        f"- generated_at: {generated_at}\n"
        f"- project_root: {project_root}\n"
        f"- project_name: {project_name}\n"
        f"- scanned_files: {len(files)}\n"
        f"- confidence: {confidence}\n\n"
        "## Top-Level Coverage\n\n"
        + "\n".join(f"- `{k}`: {v}" for k, v in sorted(by_prefix.items()))
        + "\n\n## Inferred Keywords\n\n"
        + ("\n".join(f"- `{k}`" for k in keywords) if keywords else "- `unknown`")
        + "\n\n## Unknowns\n\n"
        + ("\n".join(f"- {u}" for u in unknowns) if unknowns else "- none")
        + "\n"
    )
    runtime_arch = (
        "# Runtime Architecture\n\n"
        f"- generated_at: {generated_at}\n"
        f"- script_count: {script_signals['script_count']}\n"
        f"- scene_count: {scene_signals['scene_count']}\n\n"
        "## Script Class Signals\n\n"
        + ("\n".join(f"- `{x}`" for x in script_signals["class_names"]) if script_signals["class_names"] else "- none")
        + "\n\n## Scene Root Signals\n\n"
        + (
            "\n".join(
                f"- `{x['scene']}` => `{x['root_name']}` (`{x['root_type']}`)" for x in scene_signals["root_nodes"]
            )
            if scene_signals["root_nodes"]
            else "- none"
        )
        + "\n"
    )
    test_surface = (
        "# Test Surface\n\n"
        f"- generated_at: {generated_at}\n\n"
        "## Candidate Hooks\n\n"
        f"- scripts: {script_signals['script_count']}\n"
        f"- scenes: {scene_signals['scene_count']}\n"
        f"- docs: {by_prefix.get('docs', 0)}\n"
        f"- flows: {by_prefix.get('flows', 0)}\n\n"
        "## TODO / FIXME Signals\n\n"
        + (
            "\n".join(f"- `{x['file']}`:{x['line']} {x['text']}" for x in todo_signals[:30])
            if todo_signals
            else "- none"
        )
        + "\n"
    )
    flow_guide = (
        "# Flow Authoring Guide\n\n"
        f"- generated_at: {generated_at}\n"
        f"- confidence: {confidence}\n\n"
        "## Rules\n\n"
        "- Prefer explicit action and verify pairs.\n"
        "- Use scene and script signals from `index.json` to pick stable targets.\n"
        "- If confidence < 0.6, generate conservative smoke flows first.\n"
        "- After major refactor, call `refresh_project_context` before generating new flows.\n"
        "- Read `06-operational-profile.md` for phased runtime (menu vs post-`change_scene`) before authoring flows.\n"
        "- Before extending `design_game_basic_test_flow` output, read **§ 按游戏类型的流程预期** below and the full reference in the PointerGPF repo: `docs/mcp-basic-test-flow-game-type-expectations.md`.\n\n"
        "## 按游戏类型的流程预期（思考参照）\n\n"
        "- 目的：在步数有限时，仍尽量覆盖「进入可玩态 → 一条核心交互 → 可观察结果」；一切必须以 `flow_candidates`、`06-operational-profile.md`（含静态可点性）中的**证据**为准。\n"
        "- 未完成或未接入的功能不要写进步骤；证据不足时接受 `blocked` 或保守冒烟，并看 `generation_evidence`。\n"
        "- 完整表与说明见仓库文档（上路径）；下为速查。\n\n"
        "| 类型线索 | 进入可玩态后优先覆盖 |\n"
        "|----------|----------------------|\n"
        "| FPS / 第一人称 | 移动或视角相关一次；若自动化仅 UI，则进关后点一条 HUD/模式相关控件 |\n"
        "| 平台 / 横版 | 进第一关；跳跃或移动；仅菜单自动化则「开始」+ 关卡 UI 断言 |\n"
        "| RTS / 塔防 / 建造 | 进战斗或沙盘；选单位、放塔、开波次之一（有候选才写） |\n"
        "| 回合制 / 卡牌 | 进对局；结束回合或出牌或「开始对战」之一 |\n"
        "| 解谜 / 叙事 | 进首个可互动场景；与谜题或对话相关的一次点击 |\n"
        "| 竞速 / 体育 | 开赛；暂停或设置其一作为可观察点 |\n"
        "| 休闲 / 超休闲 | 开始 → 单局内最小操作 → 分数或重开 |\n"
        "| 纯菜单 / UI 驱动 | 主路径 + 子面板往返（如设置→返回） |\n"
        "| RPG / 开放世界（重内容） | 新游戏/继续 → 可操作角色态 → 地图或背包（有证据才写） |\n"
        "| 联网 / 多人 | 通常仅测到大厅/登录 UI；勿假设匹配成功 |\n\n"
        "- **用法与自然语言**：可调用 MCP 工具 `get_basic_test_flow_reference_guide` 获取本段与触发说明全文；"
        "用户说「基础测试流程怎么用」「流程预期说明」等时，`route_nl_intent` 可路由到该工具。仓库文档：`docs/mcp-basic-test-flow-reference-usage.md`。\n\n"
        "## Refresh Delta\n\n"
        f"- added: {delta['added_count']}\n"
        f"- removed: {delta['removed_count']}\n"
        f"- changed: {delta['changed_count']}\n"
    )
    flow_catalog = _flow_candidates_markdown(flow_candidates)

    op_bundle = build_operational_profile_bundle(
        project_root,
        script_signals=script_signals,
        scene_signals=scene_signals,
        inferred_keywords=keywords,
    )

    fingerprints = {f.rel: f.fingerprint() for f in files}
    index = {
        "generated_at": generated_at,
        "project_root": str(project_root),
        "project_name": project_name,
        "confidence": confidence,
        "unknowns": unknowns,
        "source_paths": sorted({f.top for f in files}),
        "source_counts": by_prefix,
        "suffix_counts": by_suffix,
        "inferred_keywords": keywords,
        "delta": delta,
        "script_signals": script_signals,
        "scene_signals": scene_signals,
        "data_signals": data_signals,
        "flow_candidates": flow_candidates,
        "operational_profile": op_bundle.data,
        "todo_signals": todo_signals[:80],
        "documents": {
            "overview": "01-project-overview.md",
            "runtime_architecture": "02-runtime-architecture.md",
            "test_surface": "03-test-surface.md",
            "flow_authoring_guide": "04-flow-authoring-guide.md",
            "flow_candidate_catalog": "05-flow-candidate-catalog.md",
            "operational_profile": "06-operational-profile.md",
        },
        "config_sources": cfg.config_sources,
        "effective_config": {
            "plugin_id": cfg.plugin_id,
            "plugin_cfg_rel": cfg.plugin_cfg_rel,
            "context_dir_rel": cfg.context_dir_rel,
            "index_rel": cfg.index_rel,
            "seed_flow_dir_rel": cfg.seed_flow_dir_rel,
            "report_dir_rel": cfg.report_dir_rel,
            "exp_dir_rel": cfg.exp_dir_rel,
            "scan_roots": cfg.scan_roots,
            "plugin_template_dir": str(cfg.plugin_template_dir),
        },
        "file_fingerprints": fingerprints,
    }
    _write_text(context_dir / "01-project-overview.md", overview)
    _write_text(context_dir / "02-runtime-architecture.md", runtime_arch)
    _write_text(context_dir / "03-test-surface.md", test_surface)
    _write_text(context_dir / "04-flow-authoring-guide.md", flow_guide)
    _write_text(context_dir / "05-flow-candidate-catalog.md", flow_catalog)
    _write_text(context_dir / "06-operational-profile.md", op_bundle.markdown)
    _write_text(context_dir / "index.json", json.dumps(index, ensure_ascii=False, indent=2))
    return {
        "documents": {
            "context_dir": str(context_dir),
            "overview": str(context_dir / "01-project-overview.md"),
            "runtime_architecture": str(context_dir / "02-runtime-architecture.md"),
            "test_surface": str(context_dir / "03-test-surface.md"),
            "flow_authoring_guide": str(context_dir / "04-flow-authoring-guide.md"),
            "flow_candidate_catalog": str(context_dir / "05-flow-candidate-catalog.md"),
            "operational_profile": str(context_dir / "06-operational-profile.md"),
            "index_json": str(context_dir / "index.json"),
        },
        "index": index,
    }


def _run_project_context_generation(ctx: ServerCtx, arguments: dict[str, Any], mode: str) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    max_files = int(arguments.get("max_files", 2500))
    if max_files <= 0:
        raise AppError("INVALID_ARGUMENT", "max_files must be > 0")
    files = _scan_files(project_root=project_root, scan_roots=cfg.scan_roots, limit=max_files)
    previous = _load_previous_index(project_root, cfg.index_rel)
    built = _build_context_docs(project_root=project_root, files=files, previous=previous, cfg=cfg)
    index = built["index"]
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name=f"context_{mode}",
        payload={
            "tool": f"{mode}_project_context",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "mode": mode,
            "files_scanned_count": len(files),
            "context_dir": built["documents"]["context_dir"],
            "index_json": built["documents"]["index_json"],
        },
    )
    legacy_hints = _legacy_layout_hints(project_root)
    return {
        "status": mode,
        "project_root": str(project_root),
        "files_scanned_count": len(files),
        "confidence": index["confidence"],
        "unknowns": index["unknowns"],
        "delta": index["delta"],
        "flow_candidates_summary": {
            "action_count": len(index.get("flow_candidates", {}).get("action_candidates", [])),
            "assertion_count": len(index.get("flow_candidates", {}).get("assertion_candidates", [])),
        },
        "config_sources": cfg.config_sources,
        "documents": built["documents"],
        "exp_runtime": exp_artifact,
        "legacy_layout_hints": legacy_hints,
    }


def _pick_seed_strategy(arguments: dict[str, Any], context_index: dict[str, Any]) -> str:
    allowed = {"auto", "ui", "exploration", "builder", "generic"}
    requested = str(arguments.get("strategy", "auto")).strip().lower() or "auto"
    if requested not in allowed:
        raise AppError("INVALID_ARGUMENT", f"unsupported strategy: {requested}", {"allowed": sorted(allowed)})
    if requested != "auto":
        return requested
    keywords = [
        str(x).strip().lower()
        for x in context_index.get("inferred_keywords", [])
        if isinstance(x, str) and str(x).strip()
    ]
    if "ui-heavy" in keywords:
        return "ui"
    if "exploration" in keywords:
        return "exploration"
    if "builder" in keywords:
        return "builder"
    return "generic"


def _candidate_action_step(step_id: str, candidate: dict[str, Any], fallback_action: str) -> dict[str, Any]:
    action = str(candidate.get("kind", fallback_action) or fallback_action)
    step: dict[str, Any] = {
        "id": step_id,
        "action": action,
        "candidate_id": str(candidate.get("id", "")),
        "hint": str(candidate.get("hint", "")),
    }
    target_hint = str(candidate.get("target_hint", "")).strip()
    until_hint = str(candidate.get("until_hint", "")).strip()
    if action == "click" and target_hint:
        step["target"] = {"hint": target_hint}
    if action == "wait" and until_hint:
        step["until"] = {"hint": until_hint}
        step["timeoutMs"] = 15000
    return step


def _candidate_assert_step(step_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    step: dict[str, Any] = {
        "id": step_id,
        "action": "check",
        "kind": str(candidate.get("kind", "logic_state")),
        "candidate_id": str(candidate.get("id", "")),
        "hint": str(candidate.get("hint", "")),
    }
    target_hint = str(candidate.get("target_hint", "")).strip()
    if target_hint:
        step["target"] = {"hint": target_hint}
    return step


def _derive_followup_assert(step_id: str, action_candidate: dict[str, Any]) -> dict[str, Any]:
    target_hint = str(action_candidate.get("target_hint", "")).strip()
    hint = ""
    low = target_hint.lower()
    if "openui2button" in low:
        hint = "node_visible:UI/UI2Popup"
    elif "ui3" in low or "nextbutton" in low:
        hint = "node_visible:UI/UI3"
    elif "start" in low:
        hint = "node_visible:UI/UI1"
    else:
        m = re.search(r"ui\s*([0-9]+)", low)
        if m:
            hint = f"node_visible:UI/UI{m.group(1)}"
    if hint:
        return {
            "id": step_id,
            "action": "wait",
            "kind": "logic_state",
            "hint": hint,
            "until": {"hint": hint},
            "timeoutMs": 1500,
        }
    return {
        "id": step_id,
        "action": "wait",
        "kind": "logic_state",
        "hint": f"verify feature state after {action_candidate.get('id', 'feature_action')}",
        "until": {"hint": "main_scene_ready"},
        "timeoutMs": 1500,
    }


def _seed_steps_by_strategy(
    strategy: str,
    action_candidates: list[dict[str, Any]],
    assertion_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = [f"seed_strategy={strategy}"]
    steps: list[dict[str, Any]] = [
        {"id": "launch_game", "action": "launchGame"},
        {"id": "wait_bootstrap", "action": "wait", "until": {"hint": "main_scene_ready"}, "timeoutMs": 15000},
    ]

    def action_at(index: int) -> dict[str, Any]:
        if index < len(action_candidates):
            return action_candidates[index]
        return {}

    def assert_at(index: int) -> dict[str, Any]:
        if index < len(assertion_candidates):
            return assertion_candidates[index]
        return {}

    if strategy == "ui":
        steps.append({"id": "open_ui_panel", "action": "click", "target": {"hint": "open_main_ui_panel"}})
        c0 = action_at(0)
        if c0:
            steps.append(_candidate_action_step("ui_candidate_action_1", c0, "click"))
        a0 = assert_at(0)
        if a0:
            steps.append(_candidate_assert_step("ui_assert_layout_1", a0))
        else:
            steps.append(
                {"id": "ui_assert_layout_1", "action": "check", "kind": "visual_hard", "hint": "verify ui layout"}
            )
        steps.append({"id": "snapshot_ui", "action": "snapshot", "name": "ui_state"})
        notes.append("ui-first seed: focus on panel open and visual check")
    elif strategy == "exploration":
        steps.append({"id": "enter_map", "action": "click", "target": {"hint": "open_map_or_region"}})
        c0 = action_at(0)
        if c0:
            steps.append(_candidate_action_step("explore_candidate_action_1", c0, "wait"))
        steps.append({"id": "wait_explore_tick", "action": "wait", "until": {"hint": "exploration_progress"}, "timeoutMs": 30000})
        a0 = assert_at(0)
        if a0:
            steps.append(_candidate_assert_step("explore_assert_state_1", a0))
        else:
            steps.append(
                {"id": "explore_assert_state_1", "action": "check", "kind": "logic_state", "hint": "verify explore state"}
            )
        steps.append({"id": "snapshot_explore", "action": "snapshot", "name": "explore_state"})
        notes.append("exploration seed: focus on map entry, wait, and progress assert")
    elif strategy == "builder":
        steps.append({"id": "open_build_mode", "action": "click", "target": {"hint": "open_build_ui"}})
        c0 = action_at(0)
        if c0:
            steps.append(_candidate_action_step("build_candidate_action_1", c0, "click"))
        steps.append({"id": "wait_build_complete", "action": "wait", "until": {"hint": "build_complete"}, "timeoutMs": 45000})
        a0 = assert_at(0)
        if a0:
            steps.append(_candidate_assert_step("build_assert_state_1", a0))
        else:
            steps.append(
                {"id": "build_assert_state_1", "action": "check", "kind": "logic_state", "hint": "verify build result"}
            )
        steps.append({"id": "snapshot_build", "action": "snapshot", "name": "build_state"})
        notes.append("builder seed: focus on build lifecycle and completion assert")
    else:
        c0 = action_at(0)
        c1 = action_at(1)
        if c0:
            steps.append(_candidate_action_step("candidate_action_1", c0, "click"))
        if c1:
            steps.append(_candidate_action_step("candidate_action_2", c1, "wait"))
        a0 = assert_at(0)
        if a0:
            steps.append(_candidate_assert_step("candidate_assert_1", a0))
        else:
            steps.append(
                {"id": "candidate_assert_1", "action": "check", "kind": "logic_state", "hint": "verify core state"}
            )
        steps.append({"id": "snapshot_generic", "action": "snapshot", "name": "seed_end"})
        notes.append("generic seed: use top candidates directly")

    steps.append({"id": "snapshot_end", "action": "snapshot", "name": "seed_end"})
    return steps, notes


def _step_chat_hint(step: dict[str, Any]) -> dict[str, Any]:
    action = str(step.get("action", "")).strip().lower()
    if action == "check":
        result_hint = "assertion executed"
        verify_hint = "assertion passed or failure reason recorded"
    elif action == "wait":
        result_hint = "wait window completed"
        verify_hint = "target condition reached or timeout handled"
    elif action == "snapshot":
        result_hint = "snapshot captured"
        verify_hint = "artifact path recorded"
    else:
        result_hint = "action executed"
        verify_hint = "state transition validated"
    return {
        "required_phases": ["started", "result", "verify"],
        "started_hint": f"step `{step.get('id', '')}` started",
        "result_hint": result_hint,
        "verify_hint": verify_hint,
    }


def _attach_chat_contract(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in steps:
        row = dict(step)
        row["chat_contract"] = _step_chat_hint(step)
        out.append(row)
    return out


def _load_or_build_context_index(ctx: ServerCtx, arguments: dict[str, Any], project_root: Path, cfg: RuntimeConfig) -> dict[str, Any]:
    index_path = project_root / cfg.index_rel
    if not index_path.exists():
        _run_project_context_generation(
            ctx,
            {
                **arguments,
                "project_root": str(project_root),
            },
            mode="initialized",
        )
    return _load_context_index_or_fail(project_root, cfg.index_rel)


def _save_load_capability_signals(context_index: dict[str, Any]) -> dict[str, Any]:
    corpus_parts: list[str] = []
    script_signals = context_index.get("script_signals", {})
    methods: list[str] = []
    if isinstance(script_signals, dict):
        for method in script_signals.get("method_samples", []):
            if isinstance(method, str):
                methods.append(method)
                corpus_parts.append(method)
    scene_signals = context_index.get("scene_signals", {})
    ui_tokens: list[str] = []
    if isinstance(scene_signals, dict):
        for button in scene_signals.get("button_nodes", []):
            if not isinstance(button, dict):
                continue
            name = button.get("name")
            if isinstance(name, str) and name.strip():
                ui_tokens.append(name)
                corpus_parts.append(name)
    data_signals = context_index.get("data_signals", {})
    if isinstance(data_signals, dict):
        for item in data_signals.get("top_keys", []):
            if isinstance(item, dict):
                key = item.get("key")
                if isinstance(key, str):
                    corpus_parts.append(key)
    flow_candidates = context_index.get("flow_candidates", {})
    if isinstance(flow_candidates, dict):
        for group in ("action_candidates", "assertion_candidates"):
            for item in flow_candidates.get(group, []):
                if not isinstance(item, dict):
                    continue
                for field in ("id", "hint"):
                    val = item.get(field)
                    if isinstance(val, str):
                        corpus_parts.append(val)
                target_hint = item.get("target_hint")
                if isinstance(target_hint, str) and target_hint.strip():
                    ui_tokens.append(target_hint)
                    corpus_parts.append(target_hint)
    corpus = " ".join(corpus_parts).lower()
    method_has_save = any(re.search(r"(^|_)(save|quicksave)(_|$)", m.lower()) for m in methods)
    method_has_load = any(re.search(r"(^|_)(load|quickload|readsave)(_|$)", m.lower()) for m in methods)
    ui_has_save = any(re.search(r"(save|存档|保存)", x.lower()) for x in ui_tokens)
    ui_has_load = any(re.search(r"(load|读档|读取存档)", x.lower()) for x in ui_tokens)
    has_save = method_has_save and ui_has_save
    has_load = method_has_load and ui_has_load
    return {
        "has_save": has_save,
        "has_load": has_load,
        "save_target_hint": "save_game_entry" if has_save else "",
        "load_target_hint": "load_game_entry" if has_load else "",
        "evidence": {
            "method_has_save": method_has_save,
            "method_has_load": method_has_load,
            "ui_has_save": ui_has_save,
            "ui_has_load": ui_has_load,
            "keyword_hit_save": bool(re.search(r"(save|存档|保存)", corpus)),
            "keyword_hit_load": bool(re.search(r"(load|读档|读取存档)", corpus)),
        },
    }


def _filter_action_candidates_basic(action_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered_actions: list[dict[str, Any]] = []
    for candidate in action_candidates:
        if not isinstance(candidate, dict):
            continue
        kind = str(candidate.get("kind", "")).strip().lower()
        if kind not in {"click", "wait"}:
            continue
        if kind == "click" and not str(candidate.get("target_hint", "")).strip():
            continue
        if kind == "wait" and not str(candidate.get("until_hint", "")).strip():
            continue
        filtered_actions.append(candidate)
    return filtered_actions


def _filter_candidates_for_basic_flow(
    action_candidates: list[dict[str, Any]],
    assertion_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    filtered_actions: list[dict[str, Any]] = []
    filtered_assertions: list[dict[str, Any]] = []
    reasons: list[str] = []
    for candidate in action_candidates:
        if not isinstance(candidate, dict):
            continue
        kind = str(candidate.get("kind", "")).strip().lower()
        if kind not in {"click", "wait"}:
            continue
        if kind == "click" and not str(candidate.get("target_hint", "")).strip():
            continue
        if kind == "wait" and not str(candidate.get("until_hint", "")).strip():
            continue
        filtered_actions.append(candidate)
    for candidate in assertion_candidates:
        if not isinstance(candidate, dict):
            continue
        kind = str(candidate.get("kind", "logic_state")).strip().lower() or "logic_state"
        if kind != "logic_state":
            continue
        hint = str(candidate.get("hint", "")).strip()
        if not hint:
            continue
        filtered_assertions.append(candidate)
    if not filtered_actions:
        reasons.append("no_executable_action_candidates")
    if not filtered_assertions:
        reasons.append("no_logic_assertion_candidates")
    return filtered_actions, filtered_assertions, reasons


def _tool_design_game_basic_test_flow(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    context_index = _load_or_build_context_index(ctx, arguments, project_root, cfg)
    flow_id_raw = str(arguments.get("flow_id", "")).strip() or "basic_game_test_flow"
    flow_id = _slugify(flow_id_raw)
    flow_name = str(arguments.get("flow_name", "")).strip() or "基础游戏测试流程"
    max_feature_checks = int(arguments.get("max_feature_checks", 3))
    max_feature_checks = max(1, min(max_feature_checks, 8))
    allow_low_likelihood = bool(arguments.get("allow_low_likelihood", False))

    flow_candidates = context_index.get("flow_candidates", {}) if isinstance(context_index.get("flow_candidates"), dict) else {}
    action_candidates_raw = [
        x for x in flow_candidates.get("action_candidates", []) if isinstance(x, dict) and str(x.get("id", "")).strip()
    ]
    assertion_candidates_raw = [
        x for x in flow_candidates.get("assertion_candidates", []) if isinstance(x, dict) and str(x.get("id", "")).strip()
    ]
    action_candidates, assertion_candidates, candidate_reasons = _filter_candidates_for_basic_flow(
        action_candidates_raw, assertion_candidates_raw
    )
    action_candidates = _rank_click_actions_by_static_interaction(
        action_candidates, allow_low_likelihood=allow_low_likelihood
    )
    save_load = _save_load_capability_signals(context_index)

    steps: list[dict[str, Any]] = [{"id": "launch_game", "action": "launchGame"}]
    generation_evidence: dict[str, Any] = {
        "candidate_counts": {
            "action_raw": len(action_candidates_raw),
            "assertion_raw": len(assertion_candidates_raw),
            "action_filtered": len(action_candidates),
            "assertion_filtered": len(assertion_candidates),
        },
        "save_load": save_load,
        "blocked_reasons": list(candidate_reasons),
        "selected_steps": {},
    }

    op_profile = (
        context_index.get("operational_profile") if isinstance(context_index.get("operational_profile"), dict) else {}
    )
    phase_split = split_flow_candidates_by_phase(flow_candidates, op_profile)
    transitions: list[Any] = []
    phases = op_profile.get("runtime_phases")
    if isinstance(phases, list) and len(phases) > 1 and isinstance(phases[1], dict):
        transitions = phases[1].get("scene_transitions") or []
    use_phased = bool(phase_split.get("enabled")) and isinstance(transitions, list) and len(transitions) > 0

    selected_actions: list[dict[str, Any]]
    if use_phased:
        menu_actions_raw = [x for x in phase_split.get("menu_actions", []) if isinstance(x, dict)]
        level_actions_raw = [x for x in phase_split.get("level_actions", []) if isinstance(x, dict)]
        level_assert_raw = [x for x in phase_split.get("level_assertions", []) if isinstance(x, dict)]
        menu_a = _filter_action_candidates_basic(menu_actions_raw)
        level_a = _filter_action_candidates_basic(level_actions_raw)
        level_a_f, level_ast, level_only_reasons = _filter_candidates_for_basic_flow(
            level_actions_raw, level_assert_raw
        )
        if not level_ast:
            level_a_f, level_ast, level_only_reasons = _filter_candidates_for_basic_flow(
                level_actions_raw, assertion_candidates_raw
            )
        # Prefer filtered level click actions; keep assertions aligned to level phase.
        level_a = level_a_f or level_a
        menu_a = _rank_click_actions_by_static_interaction(menu_a, allow_low_likelihood=allow_low_likelihood)
        level_a = _rank_click_actions_by_static_interaction(level_a, allow_low_likelihood=allow_low_likelihood)
        generation_evidence["candidate_counts"]["phased"] = {
            "menu_action_raw": len(menu_actions_raw),
            "level_action_raw": len(level_actions_raw),
            "menu_action_filtered": len(menu_a),
            "level_action_filtered": len(level_a),
        }
        generation_evidence["phased_generation"] = True
        generation_evidence["scene_transitions"] = transitions
        entry_action = pick_enter_game_candidate(menu_a) or (menu_a[0] if menu_a else None)
        if entry_action is None:
            exp_artifact = _write_exp_runtime_artifact(
                project_root=project_root,
                cfg=cfg,
                artifact_name="basic_game_test_flow_last",
                payload={
                    "tool": "design_game_basic_test_flow",
                    "generated_at": _utc_iso(),
                    "project_root": str(project_root),
                    "flow_id": flow_id,
                    "status": "blocked",
                    "reasons": ["no_menu_phase_actions_for_scene_change"],
                    "generation_evidence": generation_evidence,
                },
            )
            return {
                "status": "blocked",
                "project_root": str(project_root),
                "flow_id": flow_id,
                "flow_file": "",
                "step_count": 0,
                "selected_feature_checks": 0,
                "save_load_signals": save_load,
                "reasons": ["no_menu_phase_actions_for_scene_change"],
                "generation_evidence": generation_evidence,
                "exp_runtime": exp_artifact,
            }
        selected_actions = [entry_action] + level_a[:max_feature_checks]
        assertion_candidates = level_ast
        candidate_reasons = [x for x in level_only_reasons if x]
        generation_evidence["blocked_reasons"] = list(candidate_reasons)
    else:
        selected_actions = action_candidates[:max_feature_checks]

    if not selected_actions:
        exp_artifact = _write_exp_runtime_artifact(
            project_root=project_root,
            cfg=cfg,
            artifact_name="basic_game_test_flow_last",
            payload={
                "tool": "design_game_basic_test_flow",
                "generated_at": _utc_iso(),
                "project_root": str(project_root),
                "flow_id": flow_id,
                "status": "blocked",
                "reasons": candidate_reasons or ["no_executable_action_candidates"],
                "generation_evidence": generation_evidence,
            },
        )
        return {
            "status": "blocked",
            "project_root": str(project_root),
            "flow_id": flow_id,
            "flow_file": "",
            "step_count": 0,
            "selected_feature_checks": 0,
            "save_load_signals": save_load,
            "reasons": candidate_reasons or ["no_executable_action_candidates"],
            "generation_evidence": generation_evidence,
            "exp_runtime": exp_artifact,
        }

    entry_action = selected_actions[0]
    steps.append(_candidate_action_step("enter_game", entry_action, "click"))
    generation_evidence["selected_steps"]["enter_game"] = {
        "candidate_id": str(entry_action.get("id", "")),
        "evidence": entry_action.get("evidence", []),
    }
    if save_load["has_save"]:
        steps.append({"id": "save_game_smoke", "action": "click", "target": {"hint": save_load["save_target_hint"]}})
        steps.append({"id": "assert_save_success", "action": "check", "kind": "logic_state", "hint": "save completed"})
    if save_load["has_load"]:
        steps.append({"id": "load_game_smoke", "action": "click", "target": {"hint": save_load["load_target_hint"]}})
        steps.append({"id": "assert_load_success", "action": "check", "kind": "logic_state", "hint": "load completed"})

    for idx, candidate in enumerate(selected_actions[1:], start=1):
        steps.append(_candidate_action_step(f"feature_action_{idx}", candidate, "click"))
        generation_evidence["selected_steps"][f"feature_action_{idx}"] = {
            "candidate_id": str(candidate.get("id", "")),
            "evidence": candidate.get("evidence", []),
        }
        if idx <= len(assertion_candidates):
            selected_assertion = assertion_candidates[idx - 1]
            selected_hint = str(selected_assertion.get("target_hint", "")).strip().lower()
            if selected_hint in {"node_visible:ui", "node_exists:ui", "node_name:ui"}:
                steps.append(_derive_followup_assert(f"feature_assert_{idx}", candidate))
                generation_evidence["selected_steps"][f"feature_assert_{idx}"] = {"candidate_id": "", "evidence": []}
            else:
                steps.append(_candidate_assert_step(f"feature_assert_{idx}", selected_assertion))
                generation_evidence["selected_steps"][f"feature_assert_{idx}"] = {
                    "candidate_id": str(selected_assertion.get("id", "")),
                    "evidence": selected_assertion.get("evidence", []),
                }
        else:
            steps.append(_derive_followup_assert(f"feature_assert_{idx}", candidate))
            generation_evidence["selected_steps"][f"feature_assert_{idx}"] = {"candidate_id": "", "evidence": []}
    if not any(str(step.get("id", "")).startswith("feature_assert_") for step in steps):
        if assertion_candidates:
            first_assertion = assertion_candidates[0]
            first_hint = str(first_assertion.get("target_hint", "")).strip().lower()
            if first_hint in {"node_visible:ui", "node_exists:ui", "node_name:ui"}:
                steps.append(_derive_followup_assert("feature_assert_1", entry_action))
                generation_evidence["selected_steps"]["feature_assert_1"] = {"candidate_id": "", "evidence": []}
            else:
                steps.append(_candidate_assert_step("feature_assert_1", first_assertion))
                generation_evidence["selected_steps"]["feature_assert_1"] = {
                    "candidate_id": str(first_assertion.get("id", "")),
                    "evidence": first_assertion.get("evidence", []),
                }
        else:
            steps.append(_derive_followup_assert("feature_assert_1", entry_action))
            generation_evidence["selected_steps"]["feature_assert_1"] = {"candidate_id": "", "evidence": []}
    steps.append({"id": "snapshot_end", "action": "snapshot", "name": "basic_test_end"})
    seeded_steps = _attach_chat_contract(steps)

    payload = {
        "flowId": flow_id,
        "name": flow_name,
        "flow_kind": "basic_game_test",
        "generated_by": cfg.server_name,
        "generated_at": _utc_iso(),
        "source_context_index": cfg.index_rel,
        "trigger_phrases": [
            "设计游戏基础测试流程",
            "根据游戏当前状态,更新设计游戏基础设计流程",
        ],
        "steps": seeded_steps,
        "notes": [
            "Focus: evidence-driven minimal flow (entry interaction + verification + snapshot).",
            "Save/Load steps are included only when both script and UI entry evidence are detected.",
            f"selected_feature_checks={len(selected_actions)}",
            f"phased_by_operational_profile={use_phased}",
            f"operational_profile_doc={cfg.context_dir_rel}/06-operational-profile.md",
        ],
        "generation_evidence": generation_evidence,
    }

    output_raw = str(arguments.get("output_file", "")).strip()
    if output_raw:
        output_path = Path(output_raw).resolve()
    else:
        output_path = (project_root / cfg.seed_flow_dir_rel / f"{flow_id}.json").resolve()
    _write_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="basic_game_test_flow_last",
        payload={
            "tool": "design_game_basic_test_flow",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "flow_id": flow_id,
            "flow_file": str(output_path),
            "selected_feature_checks": len(selected_actions),
            "save_load_signals": save_load,
            "generation_evidence": generation_evidence,
        },
    )
    return {
        "status": "generated",
        "project_root": str(project_root),
        "flow_id": flow_id,
        "flow_file": str(output_path),
        "step_count": len(seeded_steps),
        "selected_feature_checks": len(selected_actions),
        "save_load_signals": save_load,
        "generation_evidence": generation_evidence,
        "exp_runtime": exp_artifact,
    }


def _tool_update_game_basic_design_flow_by_current_state(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    refresh_result = _run_project_context_generation(
        ctx,
        {
            **arguments,
            "project_root": str(project_root),
        },
        mode="refreshed",
    )
    designed = _tool_design_game_basic_test_flow(
        ctx,
        {
            **arguments,
            "project_root": str(project_root),
        },
    )
    _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="basic_game_test_flow_update_last",
        payload={
            "tool": "update_game_basic_design_flow_by_current_state",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "context_refresh_status": refresh_result.get("status"),
            "flow_file": designed.get("flow_file"),
        },
    )
    return {
        "status": "updated",
        "project_root": str(project_root),
        "context_refresh": {
            "status": refresh_result.get("status"),
            "delta": refresh_result.get("delta"),
            "confidence": refresh_result.get("confidence"),
        },
        "flow_result": designed,
    }


def _tool_generate_flow_seed(_ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(_ctx, arguments, project_root=project_root)
    context_index = _load_context_index_or_fail(project_root, cfg.index_rel)
    flow_id_raw = str(arguments.get("flow_id", "")).strip() or f"seed_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    flow_id = _slugify(flow_id_raw)
    flow_name = str(arguments.get("flow_name", "")).strip() or "Auto generated flow seed"
    candidates = context_index.get("flow_candidates", {}) if isinstance(context_index.get("flow_candidates"), dict) else {}
    action_candidates = [
        x for x in candidates.get("action_candidates", []) if isinstance(x, dict) and str(x.get("id", "")).strip()
    ]
    assertion_candidates = [
        x for x in candidates.get("assertion_candidates", []) if isinstance(x, dict) and str(x.get("id", "")).strip()
    ]
    strategy = _pick_seed_strategy(arguments, context_index)
    steps, strategy_notes = _seed_steps_by_strategy(
        strategy=strategy,
        action_candidates=action_candidates,
        assertion_candidates=assertion_candidates,
    )
    seeded_steps = _attach_chat_contract(steps)

    payload = {
        "flowId": flow_id,
        "name": flow_name,
        "seed_strategy": strategy,
        "chat_protocol_mode": "three_phase",
        "chat_contract_version": "v1",
        "generated_by": cfg.server_name,
        "generated_at": _utc_iso(),
        "source_context_index": cfg.index_rel,
        "steps": seeded_steps,
        "notes": [
            "This is a generated seed. Replace hints with concrete targets.",
            "Run refresh_project_context after major project changes.",
            "Each step includes chat_contract for started/result/verify compatibility.",
        ]
        + strategy_notes,
    }

    output_raw = str(arguments.get("output_file", "")).strip()
    if output_raw:
        output_path = Path(output_raw).resolve()
    else:
        output_path = (project_root / cfg.seed_flow_dir_rel / f"{flow_id}.json").resolve()
    _write_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="flow_seed_last",
        payload={
            "tool": "generate_flow_seed",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "flow_id": flow_id,
            "flow_file": str(output_path),
            "seed_strategy": strategy,
            "step_count": len(seeded_steps),
        },
    )
    legacy_hints = _legacy_layout_hints(project_root)
    return {
        "status": "generated",
        "project_root": str(project_root),
        "flow_id": flow_id,
        "flow_file": str(output_path),
        "seed_strategy": strategy,
        "step_count": len(seeded_steps),
        "from_action_candidates": len(action_candidates),
        "from_assertion_candidates": len(assertion_candidates),
        "exp_runtime": exp_artifact,
        "legacy_layout_hints": legacy_hints,
    }


def _diagnostics_to_issue_text(d: dict[str, Any]) -> str:
    summary = str(d.get("summary", "")).strip()
    items = d.get("items")
    chunks: list[str] = []
    if summary:
        chunks.append(summary)
    if isinstance(items, list):
        for it in items[:3]:
            if isinstance(it, dict):
                msg = str(it.get("message", "")).strip()
                if msg:
                    chunks.append(msg)
    out = " | ".join(chunks)
    return out if out else "runtime diagnostics reported error/fatal"


def _tool_run_game_basic_test_flow_execute(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    flow_file_raw = str(arguments.get("flow_file", "")).strip()
    if flow_file_raw:
        flow_file = Path(flow_file_raw)
        if not flow_file.is_absolute():
            flow_file = (project_root / flow_file).resolve()
        else:
            flow_file = flow_file.resolve()
    else:
        flow_id = str(arguments.get("flow_id", "")).strip() or "basic_game_test_flow"
        flow_slug = _slugify(flow_id)
        flow_file = (project_root / cfg.seed_flow_dir_rel / f"{flow_slug}.json").resolve()
    if not flow_file.exists() or not flow_file.is_file():
        raise AppError("INVALID_ARGUMENT", f"flow file not found: {flow_file}")
    flow_data = _read_json_file(flow_file)
    raw_timeout = arguments.get("step_timeout_ms", 30_000)
    try:
        step_timeout_ms = int(raw_timeout) if raw_timeout is not None else 30_000
    except (TypeError, ValueError):
        step_timeout_ms = 30_000
    if step_timeout_ms <= 0:
        step_timeout_ms = 30_000
    run_id_opt = str(arguments.get("run_id", "")).strip() or None
    runtime_meta = _probe_runtime_gate(project_root)
    # Non-negotiable execution policy:
    # 1) run in real play mode runtime gate
    # 2) emit step-level shell-visible progress
    require_play_mode = True
    shell_report = True
    close_project_on_finish = bool(arguments.get("close_project_on_finish", True))
    auto_enter_requested = False
    engine_bootstrap: dict[str, Any] = {}
    if not bool(runtime_meta.get("runtime_gate_passed", False)):
        runtime_meta, engine_bootstrap = _ensure_runtime_play_mode(project_root, arguments)
        auto_enter_requested = bool(engine_bootstrap.get("auto_enter_play_mode_requested", False))
    if not bool(runtime_meta.get("runtime_gate_passed", False)):
        close_meta = _maybe_request_project_close(project_root, close_project_on_finish)
        _rgf_details: dict[str, Any] = {
            "runtime_mode": runtime_meta.get("runtime_mode", "editor_bridge"),
            "runtime_entry": runtime_meta.get("runtime_entry", "unknown"),
            "runtime_gate_passed": False,
            "auto_enter_play_mode_requested": auto_enter_requested,
            "engine_bootstrap": engine_bootstrap,
            "blocking_point": "runtime_gate_not_passed_after_bootstrap_attempt",
            "next_actions": [
                "check project_root points to intended project",
                "set godot_executable or tools/game-test-runner/config/godot_executable.json",
                "re-run run_game_basic_test_flow after engine starts and enters play mode",
            ],
            "project_close": close_meta,
        }
        _attach_hard_teardown(_rgf_details, project_root, arguments, close_meta)
        raise AppError(
            "RUNTIME_GATE_FAILED",
            "play mode is required before executing flow (strict policy)",
            _rgf_details,
        )
    runtime_dir = _exp_runtime_dir(project_root, cfg)
    opts = FlowRunOptions(
        project_root=project_root,
        flow_file=flow_file,
        report_dir=runtime_dir,
        step_timeout_ms=step_timeout_ms,
        run_id=run_id_opt,
        fail_fast=bool(arguments.get("fail_fast", True)),
        shell_report=shell_report,
        runtime_meta=runtime_meta,
        observe_engine_errors=bool(arguments.get("observe_engine_errors", True)),
    )
    runner = FlowRunner(opts)
    try:
        report = runner.run(flow_data)
    except FlowExecutionTimeout as exc:
        close_meta = _maybe_request_project_close(project_root, close_project_on_finish)
        rep = exc.report or {}
        dual = build_dual_conclusions(rep)
        _to_details: dict[str, Any] = {
            "run_id": exc.run_id,
            "step_index": exc.step_index,
            "step_id": exc.step_id,
            "execution_report": rep,
            "tool_usability": dual["tool_usability"],
            "gameplay_runnability": dual["gameplay_runnability"],
            "step_broadcast_summary": rep.get("step_broadcast_summary"),
            "project_close": close_meta,
            "diagnostics_file_rel": "pointer_gpf/tmp/runtime_diagnostics.json",
            "blocking_point": "file_bridge_no_response_within_step_timeout",
            "next_actions": [
                "confirm PointerGPF plugin autoload is running in play mode",
                "inspect pointer_gpf/tmp/runtime_diagnostics.json for engine-side errors",
                "inspect pointer_gpf/tmp/response.json and command.json pairing",
            ],
            "suggested_next_tool": "auto_fix_game_bug",
            "auto_fix_arguments_suggestion": {
                "issue": (
                    f"basic flow step timed out (no bridge response): step_id={exc.step_id!r} run_id={exc.run_id!r}: {exc}"
                ),
                "max_cycles": 3,
            },
        }
        _attach_hard_teardown(_to_details, project_root, arguments, close_meta)
        raise AppError("TIMEOUT", str(exc), _to_details) from exc
    except FlowExecutionStepFailed as exc:
        close_meta = _maybe_request_project_close(project_root, close_project_on_finish)
        rep = exc.report or {}
        dual = build_dual_conclusions(rep)
        _sf_details: dict[str, Any] = {
            "run_id": exc.run_id,
            "step_index": exc.step_index,
            "step_id": exc.step_id,
            "execution_report": rep,
            "tool_usability": dual["tool_usability"],
            "gameplay_runnability": dual["gameplay_runnability"],
            "step_broadcast_summary": rep.get("step_broadcast_summary"),
            "project_close": close_meta,
            "diagnostics_file_rel": "pointer_gpf/tmp/runtime_diagnostics.json",
            "suggested_next_tool": "auto_fix_game_bug",
            "auto_fix_arguments_suggestion": {
                "issue": f"basic flow step failed: {exc.step_id}: {str(exc)}",
                "max_cycles": 3,
            },
        }
        _attach_hard_teardown(_sf_details, project_root, arguments, close_meta)
        raise AppError("STEP_FAILED", str(exc), _sf_details) from exc
    except FlowExecutionEngineStalled as exc:
        close_meta = _maybe_request_project_close(project_root, close_project_on_finish)
        rep = exc.report or {}
        dual = build_dual_conclusions(rep)
        _es_details: dict[str, Any] = {
            "run_id": exc.run_id,
            "step_index": exc.step_index,
            "step_id": exc.step_id,
            "execution_report": rep,
            "runtime_diagnostics": exc.diagnostics,
            "diagnostics_file_rel": "pointer_gpf/tmp/runtime_diagnostics.json",
            "tool_usability": dual["tool_usability"],
            "gameplay_runnability": dual["gameplay_runnability"],
            "step_broadcast_summary": rep.get("step_broadcast_summary"),
            "project_close": close_meta,
            "blocking_point": "runtime_diagnostics_error_or_fatal_while_waiting_for_bridge",
            "next_actions": [
                "fix script or scene errors indicated in runtime_diagnostics.items",
                "or call auto_fix_game_bug with auto_fix_arguments_suggestion.issue",
            ],
            "suggested_next_tool": "auto_fix_game_bug",
            "auto_fix_arguments_suggestion": {
                "issue": _diagnostics_to_issue_text(exc.diagnostics),
                "max_cycles": 3,
            },
        }
        _attach_hard_teardown(_es_details, project_root, arguments, close_meta)
        raise AppError("ENGINE_RUNTIME_STALLED", str(exc), _es_details) from exc
    close_meta = _maybe_request_project_close(project_root, close_project_on_finish)
    legacy_hints = _legacy_layout_hints(project_root)
    dual = build_dual_conclusions(report)
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="basic_game_test_execution_last",
        payload={
            "tool": "run_game_basic_test_flow",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "flow_file": str(flow_file),
            "flow_id": str(flow_data.get("flowId", "")),
            "run_id": report["run_id"],
            "status": report["status"],
            "execution_report": report,
            "tool_usability": dual["tool_usability"],
            "gameplay_runnability": dual["gameplay_runnability"],
            "step_broadcast_summary": report.get("step_broadcast_summary"),
            "project_close": close_meta,
        },
    )
    return {
        "status": report.get("status", "passed"),
        "project_root": str(project_root),
        "flow_file": str(flow_file),
        "execution_report": report,
        "tool_usability": dual["tool_usability"],
        "gameplay_runnability": dual["gameplay_runnability"],
        "step_broadcast_summary": report.get("step_broadcast_summary"),
        "project_close": close_meta,
        "exp_runtime": exp_artifact,
        "legacy_layout_hints": legacy_hints,
    }


def _tool_run_game_basic_test_flow_with_repair_loop(
    ctx: ServerCtx,
    arguments: dict[str, Any],
    *,
    max_repair_rounds: int,
    auto_fix_max_cycles: int,
) -> dict[str, Any]:
    fix_base = dict(arguments)
    project_root = _resolve_project_root(arguments)
    rounds: list[dict[str, Any]] = []
    last_out: dict[str, Any] | None = None
    for idx in range(max_repair_rounds):
        entry: dict[str, Any] = {"round_index": idx + 1, "max_rounds": max_repair_rounds}
        try:
            last_out = _tool_run_game_basic_test_flow_execute(ctx, arguments)
        except AppError as exc:
            if str(exc.code or "") in _NON_REPAIRABLE_FLOW_APP_CODES:
                raise
            entry["flow_phase"] = "exception"
            entry["flow_error"] = exc.as_dict()
            issue = _issue_text_from_flow_app_error(exc)
            entry.update(
                _auto_repair_round_for_flow_exception(
                    ctx, fix_base, project_root, exc, issue, auto_fix_max_cycles
                )
            )
            rounds.append(entry)
            continue
        entry["flow_phase"] = "returned"
        top_status = str(last_out.get("status", "")).strip()
        er = last_out.get("execution_report") if isinstance(last_out.get("execution_report"), dict) else {}
        exec_status = str(er.get("status", top_status)).strip()
        entry["flow_snapshot"] = {"execution_status": exec_status}
        if exec_status == "passed":
            entry["outcome"] = "passed"
            rounds.append(entry)
            merged = dict(last_out)
            merged["auto_repair"] = {
                "enabled": True,
                "final_status": "passed",
                "rounds": rounds,
                "remediation_traces": _merge_remediation_traces_from_rounds(rounds),
            }
            return merged
        issue = _issue_text_from_execution_payload(last_out)
        entry.update(
            _auto_repair_round_for_flow_failed_payload(
                ctx, fix_base, project_root, last_out, issue, auto_fix_max_cycles
            )
        )
        rounds.append(entry)
    exhaust: dict[str, Any] = dict(last_out) if last_out else {"status": "failed"}
    exhaust["auto_repair"] = {
        "enabled": True,
        "final_status": "exhausted_rounds",
        "rounds": rounds,
        "remediation_traces": _merge_remediation_traces_from_rounds(rounds),
    }
    return exhaust


def _tool_run_game_basic_test_flow(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    auto_repair, max_rr, fix_c = _parse_auto_repair_params(arguments)
    if not auto_repair:
        return _tool_run_game_basic_test_flow_execute(ctx, arguments)
    return _tool_run_game_basic_test_flow_with_repair_loop(
        ctx, arguments, max_repair_rounds=max_rr, auto_fix_max_cycles=fix_c
    )


def _tool_run_game_basic_test_flow_by_current_state_once(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    refreshed = _tool_update_game_basic_design_flow_by_current_state(ctx, {**arguments, "project_root": str(project_root)})
    flow_result = refreshed.get("flow_result", {})
    if not isinstance(flow_result, dict):
        flow_result = {}
    if str(flow_result.get("status", "")).strip() == "blocked":
        raise AppError(
            "FLOW_GENERATION_BLOCKED",
            "cannot run basic flow because generation is blocked by missing executable evidence",
            {
                "flow_result": flow_result,
                "context_refresh": refreshed.get("context_refresh", {}),
            },
        )
    run_args = {
        **arguments,
        "project_root": str(project_root),
        "flow_file": str(flow_result.get("flow_file", "")).strip(),
        "require_play_mode": True,
        "shell_report": True,
        "auto_repair": False,
    }
    executed = _tool_run_game_basic_test_flow(ctx, run_args)
    return {
        "status": executed.get("status", "failed"),
        "context_refresh": refreshed.get("context_refresh", {}),
        "flow_result": flow_result,
        "execution_result": executed,
    }


def _tool_run_game_basic_test_flow_by_current_state_with_repair(
    ctx: ServerCtx,
    arguments: dict[str, Any],
    max_repair_rounds: int,
    auto_fix_max_cycles: int,
) -> dict[str, Any]:
    fix_base = dict(arguments)
    project_root = _resolve_project_root(arguments)
    rounds: list[dict[str, Any]] = []
    last_out: dict[str, Any] | None = None
    for idx in range(max_repair_rounds):
        entry: dict[str, Any] = {"round_index": idx + 1, "max_rounds": max_repair_rounds}
        try:
            last_out = _tool_run_game_basic_test_flow_by_current_state_once(ctx, arguments)
        except AppError as exc:
            if str(exc.code or "") in _NON_REPAIRABLE_FLOW_APP_CODES:
                raise
            entry["flow_phase"] = "exception"
            entry["flow_error"] = exc.as_dict()
            issue = _issue_text_from_flow_app_error(exc)
            entry.update(
                _auto_repair_round_for_flow_exception(
                    ctx, fix_base, project_root, exc, issue, auto_fix_max_cycles
                )
            )
            rounds.append(entry)
            continue
        entry["flow_phase"] = "returned"
        er = last_out.get("execution_result") if isinstance(last_out.get("execution_result"), dict) else {}
        st = str(er.get("status", "")).strip()
        entry["flow_snapshot"] = {"execution_status": st}
        if st == "passed":
            entry["outcome"] = "passed"
            rounds.append(entry)
            merged = dict(last_out)
            merged["auto_repair"] = {
                "enabled": True,
                "final_status": "passed",
                "rounds": rounds,
                "remediation_traces": _merge_remediation_traces_from_rounds(rounds),
            }
            return merged
        issue = _issue_text_from_execution_payload(er)
        entry.update(
            _auto_repair_round_for_flow_failed_payload(
                ctx, fix_base, project_root, er, issue, auto_fix_max_cycles
            )
        )
        rounds.append(entry)
    exhaust: dict[str, Any] = dict(last_out) if last_out else {"status": "failed"}
    exhaust["auto_repair"] = {
        "enabled": True,
        "final_status": "exhausted_rounds",
        "rounds": rounds,
        "remediation_traces": _merge_remediation_traces_from_rounds(rounds),
    }
    return exhaust


def _tool_run_game_basic_test_flow_by_current_state(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    auto_repair, max_rr, fix_c = _parse_auto_repair_params(arguments)
    if not auto_repair:
        return _tool_run_game_basic_test_flow_by_current_state_once(ctx, arguments)
    return _tool_run_game_basic_test_flow_by_current_state_with_repair(ctx, arguments, max_rr, fix_c)


_ORCHESTRATION_STRIPPED_KEYS = frozenset(
    {"orchestration_explicit_opt_in", "max_orchestration_rounds", "auto_fix_max_cycles"}
)


def _tool_run_basic_test_flow_orchestrated(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    """Legacy explicit-opt-in tool: delegates to run_game_basic_test_flow_by_current_state with auto_repair enabled.

    New integrations should call run_game_basic_test_flow_by_current_state with auto_repair=true (default)
    and max_repair_rounds / auto_fix_max_cycles directly; this tool remains for backward compatibility.
    """
    if not bool(arguments.get("orchestration_explicit_opt_in", False)):
        raise AppError(
            "INVALID_ARGUMENT",
            "orchestration_explicit_opt_in must be true (legacy orchestration entry; high cost)",
            {
                "fix": "read docs/mcp-basic-test-flow-reference-usage.md and set orchestration_explicit_opt_in=true",
                "blocking_point": "orchestration_opt_in_required",
            },
        )
    raw_max = arguments.get("max_orchestration_rounds", 2)
    try:
        max_rounds = int(raw_max) if raw_max is not None else 2
    except (TypeError, ValueError):
        raise AppError("INVALID_ARGUMENT", "max_orchestration_rounds must be an integer")
    if max_rounds < 1 or max_rounds > 8:
        raise AppError("INVALID_ARGUMENT", "max_orchestration_rounds must be between 1 and 8")
    raw_fix = arguments.get("auto_fix_max_cycles", 3)
    try:
        fix_cycles = int(raw_fix) if raw_fix is not None else 3
    except (TypeError, ValueError):
        raise AppError("INVALID_ARGUMENT", "auto_fix_max_cycles must be an integer")
    if fix_cycles < 0:
        raise AppError("INVALID_ARGUMENT", "auto_fix_max_cycles must be >= 0")
    project_root = _resolve_project_root(arguments)
    run_merged = {k: v for k, v in arguments.items() if k not in _ORCHESTRATION_STRIPPED_KEYS}
    run_merged["auto_repair"] = True
    run_merged["max_repair_rounds"] = max_rounds
    run_merged["auto_fix_max_cycles"] = fix_cycles
    inner = _tool_run_game_basic_test_flow_by_current_state(ctx, run_merged)
    ar = inner.get("auto_repair") if isinstance(inner.get("auto_repair"), dict) else {}
    rounds = ar.get("rounds") if isinstance(ar.get("rounds"), list) else []
    fs_inner = str(ar.get("final_status", "")).strip()
    er = inner.get("execution_result") if isinstance(inner.get("execution_result"), dict) else {}
    st = str(er.get("status", "")).strip()
    if fs_inner == "passed" or st == "passed":
        final_status = "passed"
    else:
        final_status = "exhausted_rounds" if fs_inner == "exhausted_rounds" else (fs_inner or "exhausted_rounds")
    return {
        "final_status": final_status,
        "project_root": str(project_root),
        "rounds": rounds,
        "last_flow_bundle": inner,
        "orchestration_alias": True,
        "delegates_to": "run_game_basic_test_flow_by_current_state",
    }


def _tool_auto_fix_game_bug(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    issue = str(arguments.get("issue", "")).strip()
    if not issue:
        raise AppError("INVALID_ARGUMENT", "issue is required")

    raw_max = arguments.get("max_cycles", 3)
    try:
        max_cycles = int(raw_max) if raw_max is not None else 3
    except (TypeError, ValueError):
        raise AppError("INVALID_ARGUMENT", "max_cycles must be an integer")
    if max_cycles < 0:
        raise AppError("INVALID_ARGUMENT", "max_cycles must be >= 0")

    timeout_seconds: float | None
    if arguments.get("timeout_seconds") is not None:
        try:
            timeout_seconds = float(arguments["timeout_seconds"])
        except (TypeError, ValueError):
            raise AppError("INVALID_ARGUMENT", "timeout_seconds must be a number")
        if timeout_seconds < 0:
            raise AppError("INVALID_ARGUMENT", "timeout_seconds must be >= 0")
    else:
        timeout_seconds = None

    run_args = {
        **arguments,
        "project_root": str(project_root),
        "require_play_mode": True,
        "shell_report": True,
        "auto_repair": False,
    }

    def run_verification() -> dict[str, Any]:
        try:
            out = _tool_run_game_basic_test_flow_by_current_state(ctx, run_args)
            exec_result = out.get("execution_result") or {}
            status = str(exec_result.get("status", "failed"))
            passed = status == "passed"
            return {
                "passed": passed,
                "status": status,
                "payload": out,
                "app_error": None,
            }
        except AppError as exc:
            if exc.code == "INVALID_ARGUMENT":
                raise
            code = str(exc.code or "ERROR")
            return {
                "passed": False,
                "status": code.lower(),
                "payload": None,
                "app_error": exc.as_dict(),
            }

    trace = RemediationTrace(run_id=str(project_root.resolve()))
    loop_result = run_bug_fix_loop(
        project_root=project_root,
        issue=issue,
        max_cycles=max_cycles,
        timeout_seconds=timeout_seconds,
        run_verification=run_verification,
        l2_try_patch=build_l2_try_patch_from_env(),
        trace=trace,
    )
    return {
        "final_status": loop_result["final_status"],
        "cycles_completed": loop_result["cycles_completed"],
        "loop_evidence": loop_result["loop_evidence"],
        "issue": loop_result.get("issue", issue),
        "project_root": loop_result.get("project_root", str(project_root)),
        "initial_verification": loop_result.get("initial_verification"),
        "remediation_trace": loop_result.get("remediation_trace", {"run_id": "", "events": []}),
    }


def _tool_route_nl_intent(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    text = str(arguments.get("text", "")).strip()
    if not text:
        raise AppError("INVALID_ARGUMENT", "text is required")
    routed = route_nl_intent(text)
    example_root = (ctx.repo_root / "examples" / "godot_minimal").resolve()
    return {
        "text": text,
        "target_tool": routed.target_tool,
        "reason": routed.reason,
        "canonical_example_project_rel": "examples/godot_minimal",
        "canonical_example_project_root": str(example_root),
    }


def _tool_get_basic_test_flow_reference_guide(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    """Return usage + NL trigger documentation for basic test flow references (repo markdown)."""
    cfg = _resolve_runtime_config(ctx, arguments)
    doc_rel = "docs/mcp-basic-test-flow-reference-usage.md"
    doc_path = (ctx.repo_root / "docs" / "mcp-basic-test-flow-reference-usage.md").resolve()
    status = "ok"
    if doc_path.is_file():
        markdown = doc_path.read_text(encoding="utf-8", errors="replace")
    else:
        status = "doc_missing"
        markdown = (
            f"未在 MCP 包内找到 `{doc_rel}`（期望路径: {doc_path}）。"
            "请从 PointerGPF 仓库获取该文件，或查阅目标工程内 "
            f"`{cfg.context_dir_rel}/04-flow-authoring-guide.md` 与 `{cfg.context_dir_rel}/06-operational-profile.md`。"
        )
    project_root_raw = str(arguments.get("project_root", "")).strip()
    proj_paths: dict[str, str] = {
        "flow_authoring_guide": f"{cfg.context_dir_rel}/04-flow-authoring-guide.md",
        "operational_profile": f"{cfg.context_dir_rel}/06-operational-profile.md",
        "flow_candidate_catalog": f"{cfg.context_dir_rel}/05-flow-candidate-catalog.md",
        "index_json": f"{cfg.context_dir_rel}/index.json",
    }
    if project_root_raw:
        proj_paths["project_root"] = str(Path(project_root_raw).resolve())
    return {
        "status": status,
        "repo_doc_rel": doc_rel,
        "repo_doc_path": str(doc_path),
        "related_repo_docs": [
            "docs/mcp-basic-test-flow-game-type-expectations.md",
            "docs/mcp-docs-index.md",
        ],
        "project_context_paths": proj_paths,
        "natural_language_triggers": [
            "基础测试流程怎么用",
            "流程预期说明",
            "游戏类型流程预期查看说明",
        ],
        "markdown": markdown,
    }


def _tool_figma_design_to_baseline(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    figma_file_key = str(arguments.get("figma_file_key", "")).strip()
    figma_node_id = str(arguments.get("figma_node_id", "")).strip()
    if not figma_file_key:
        raise AppError("INVALID_ARGUMENT", "figma_file_key is required")
    if not figma_node_id:
        raise AppError("INVALID_ARGUMENT", "figma_node_id is required")
    screenshot_path = _resolve_existing_file(str(arguments.get("figma_screenshot_file", "")), "figma_screenshot_file")
    context = arguments.get("figma_design_context", {})
    if context and not isinstance(context, dict):
        raise AppError("INVALID_ARGUMENT", "figma_design_context must be an object")
    context = context if isinstance(context, dict) else {}
    baseline_slug = _slugify(f"{figma_file_key}_{figma_node_id}")
    baseline_dir = _exp_runtime_dir(project_root, cfg) / "figma"
    baseline_json_path = baseline_dir / f"figma_baseline_{baseline_slug}.json"
    screenshot_copy = baseline_dir / f"figma_screenshot_{baseline_slug}.png"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    screenshot_copy = _convert_image_to_png_if_needed(screenshot_path, screenshot_copy)
    figma_metrics = _parse_png_metrics(screenshot_copy)
    payload = {
        "generated_at": _utc_iso(),
        "figma_ref": {
            "file_key": figma_file_key,
            "node_id": figma_node_id,
            "version": str(arguments.get("figma_version", "")).strip() or "latest",
        },
        "figma_screenshot_file": str(screenshot_copy),
        "figma_design_context": context,
        "expected_layout": _extract_figma_layout_expectation(context),
        "expected_image_height": float(arguments.get("image_target_height", 120)),
        "screenshot_metrics": {
            "format": figma_metrics.get("format"),
            "width": figma_metrics.get("width"),
            "height": figma_metrics.get("height"),
            "byte_size": figma_metrics.get("byte_size"),
        },
    }
    _write_text(baseline_json_path, json.dumps(payload, ensure_ascii=False, indent=2))
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="figma_baseline_last",
        payload={
            "tool": "figma_design_to_baseline",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "baseline_file": str(baseline_json_path),
            "figma_ref": payload["figma_ref"],
        },
    )
    return {
        "status": "generated",
        "project_root": str(project_root),
        "baseline_file": str(baseline_json_path),
        "figma_screenshot_file": str(screenshot_copy),
        "figma_ref": payload["figma_ref"],
        "exp_runtime": exp_artifact,
    }


def _tool_compare_figma_game_ui(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    baseline_file = _resolve_existing_file(str(arguments.get("figma_baseline_file", "")), "figma_baseline_file")
    game_snapshot_file = _resolve_existing_file(str(arguments.get("game_snapshot_file", "")), "game_snapshot_file")
    baseline = _read_json_file(baseline_file)
    figma_screenshot_file = _resolve_existing_file(
        str(baseline.get("figma_screenshot_file", "")),
        "figma_screenshot_file",
    )
    figma_metrics = _parse_png_metrics(figma_screenshot_file)
    game_metrics = _parse_png_metrics(game_snapshot_file)
    pixel_threshold = float(arguments.get("pixel_threshold", 0.03))
    perceptual_threshold = float(arguments.get("perceptual_threshold", 0.97))
    resize_to_baseline = bool(arguments.get("resize_to_baseline", True))
    same_resolution = (
        int(figma_metrics.get("width", 0)) > 0
        and int(figma_metrics.get("width", 0)) == int(game_metrics.get("width", 0))
        and int(figma_metrics.get("height", 0)) == int(game_metrics.get("height", 0))
    )
    figma_payload = figma_metrics.get("pixel_data", b"") or figma_metrics.get("raw_payload", b"") or figma_screenshot_file.read_bytes()
    game_payload = game_metrics.get("pixel_data", b"") or game_metrics.get("raw_payload", b"") or game_snapshot_file.read_bytes()
    resize_info: dict[str, Any] = {"resized_for_compare": False, "method": "raw_payload"}
    can_compare_raw = same_resolution and len(figma_payload) == len(game_payload) and len(figma_payload) > 0
    if resize_to_baseline and int(figma_metrics.get("width", 0)) > 0 and int(figma_metrics.get("height", 0)) > 0:
        pixel_diff_ratio, resize_info = _compute_resized_diff_ratio(
            figma_screenshot_file,
            game_snapshot_file,
            int(figma_metrics.get("width", 0)),
            int(figma_metrics.get("height", 0)),
        )
    elif can_compare_raw:
        pixel_diff_ratio = _byte_diff_ratio(figma_payload, game_payload)
    else:
        pixel_diff_ratio = 1.0
    perceptual_score = round(max(0.0, 1.0 - pixel_diff_ratio), 6)
    expected_layout = baseline.get("expected_layout", {})
    layout_diff = {
        "expected_width": int(expected_layout.get("width", 0) or 0),
        "expected_height": int(expected_layout.get("height", 0) or 0),
        "actual_width": int(game_metrics.get("width", 0) or 0),
        "actual_height": int(game_metrics.get("height", 0) or 0),
    }
    layout_diff["dimension_mismatch"] = bool(
        layout_diff["expected_width"]
        and layout_diff["expected_height"]
        and (
            layout_diff["expected_width"] != layout_diff["actual_width"]
            or layout_diff["expected_height"] != layout_diff["actual_height"]
        )
    )
    visual_pass = pixel_diff_ratio <= pixel_threshold and perceptual_score >= perceptual_threshold
    overall_status = "pass" if visual_pass and not layout_diff["dimension_mismatch"] else "fail"
    run_id = _slugify(f"{baseline.get('figma_ref', {}).get('file_key', 'figma')}_{datetime.now(timezone.utc).timestamp()}")
    report_payload = {
        "tool": "compare_figma_game_ui",
        "generated_at": _utc_iso(),
        "run_id": run_id,
        "project_root": str(project_root),
        "figma_ref": baseline.get("figma_ref", {}),
        "figma_baseline_file": str(baseline_file),
        "game_snapshot_file": str(game_snapshot_file),
        "overall_status": overall_status,
        "visual_diff": {
            "pixel_diff_ratio": pixel_diff_ratio,
            "perceptual_score": perceptual_score,
            "pixel_threshold": pixel_threshold,
            "perceptual_threshold": perceptual_threshold,
            "same_resolution": same_resolution,
            "raw_payload_compatible": can_compare_raw,
            "resize_to_baseline": resize_to_baseline,
            "resize_info": resize_info,
        },
        "layout_diff": layout_diff,
        "hot_regions": [],
        "next_action": "request_approval" if overall_status != "pass" else "accept",
        "hashes": {
            "figma_sha256": hashlib.sha256(figma_screenshot_file.read_bytes()).hexdigest(),
            "game_sha256": hashlib.sha256(game_snapshot_file.read_bytes()).hexdigest(),
        },
    }
    report_name = _slugify(str(arguments.get("report_basename", "")).strip() or f"compare_figma_game_ui_{run_id}")
    report_file = _exp_runtime_dir(project_root, cfg) / f"{report_name}.json"
    _write_text(report_file, json.dumps(report_payload, ensure_ascii=False, indent=2))
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="compare_figma_game_ui_last",
        payload={
            "tool": "compare_figma_game_ui",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "report_file": str(report_file),
            "overall_status": overall_status,
            "run_id": run_id,
        },
    )
    return {
        "status": "compared",
        "project_root": str(project_root),
        "report_file": str(report_file),
        "run_id": run_id,
        "overall_status": overall_status,
        "visual_diff": report_payload["visual_diff"],
        "layout_diff": layout_diff,
        "next_action": report_payload["next_action"],
        "exp_runtime": exp_artifact,
    }


def _tool_annotate_ui_mismatch(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    compare_report_file = _resolve_existing_file(str(arguments.get("compare_report_file", "")), "compare_report_file")
    compare_payload, resolved_compare_report = _resolve_compare_report_payload(compare_report_file)
    mismatches: list[dict[str, Any]] = []
    layout = compare_payload.get("layout_diff", {})
    if isinstance(layout, dict) and layout.get("dimension_mismatch"):
        mismatches.append(
            {
                "severity": "high",
                "type": "dimension_mismatch",
                "figma_ref": compare_payload.get("figma_ref", {}),
                "evidence": {
                    "expected": [layout.get("expected_width"), layout.get("expected_height")],
                    "actual": [layout.get("actual_width"), layout.get("actual_height")],
                },
            }
        )
    visual = compare_payload.get("visual_diff", {})
    if isinstance(visual, dict) and float(visual.get("pixel_diff_ratio", 0.0)) > float(visual.get("pixel_threshold", 0.03)):
        mismatches.append(
            {
                "severity": "medium",
                "type": "visual_diff",
                "figma_ref": compare_payload.get("figma_ref", {}),
                "evidence": {
                    "pixel_diff_ratio": visual.get("pixel_diff_ratio"),
                    "threshold": visual.get("pixel_threshold"),
                    "perceptual_score": visual.get("perceptual_score"),
                },
            }
        )
    annotation_payload = {
        "tool": "annotate_ui_mismatch",
        "generated_at": _utc_iso(),
        "run_id": compare_payload.get("run_id"),
        "project_root": str(project_root),
        "compare_report_file": str(resolved_compare_report),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "summary": "no mismatch" if not mismatches else "mismatch detected",
    }
    report_file = _exp_runtime_dir(project_root, cfg) / f"ui_mismatch_annotations_{_slugify(str(compare_payload.get('run_id', 'last')))}.json"
    _write_text(report_file, json.dumps(annotation_payload, ensure_ascii=False, indent=2))
    return {
        "status": "annotated",
        "project_root": str(project_root),
        "annotation_file": str(report_file),
        "mismatch_count": len(mismatches),
    }


def _tool_approve_ui_fix_plan(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    compare_report_file = _resolve_existing_file(str(arguments.get("compare_report_file", "")), "compare_report_file")
    approved = bool(arguments.get("approved", False))
    token = str(arguments.get("approval_token", "")).strip()
    if approved and not token:
        raise AppError("INVALID_ARGUMENT", "approval_token is required when approved=true")
    compare_payload, resolved_compare_report = _resolve_compare_report_payload(compare_report_file)
    run_id = _slugify(str(compare_payload.get("run_id", "last")))
    approval_payload = {
        "tool": "approve_ui_fix_plan",
        "generated_at": _utc_iso(),
        "project_root": str(project_root),
        "run_id": compare_payload.get("run_id"),
        "compare_report_file": str(resolved_compare_report),
        "approved": approved,
        "approval_token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest() if token else "",
    }
    approval_file = _exp_runtime_dir(project_root, cfg) / f"ui_fix_approval_{run_id}.json"
    _write_text(approval_file, json.dumps(approval_payload, ensure_ascii=False, indent=2))
    return {
        "status": "recorded",
        "project_root": str(project_root),
        "approval_file": str(approval_file),
        "approved": approved,
        "run_id": compare_payload.get("run_id"),
    }


def _tool_suggest_ui_fix_patch(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    compare_report_file = _resolve_existing_file(str(arguments.get("compare_report_file", "")), "compare_report_file")
    approval_file = _resolve_existing_file(str(arguments.get("approval_file", "")), "approval_file")
    compare_payload, resolved_compare_report = _resolve_compare_report_payload(compare_report_file)
    approval_payload = _read_json_file(approval_file)
    if not bool(approval_payload.get("approved", False)):
        raise AppError("INVALID_ARGUMENT", "fix suggestion requires approved=true in approval_file")
    baseline_file = _resolve_existing_file(str(compare_payload.get("figma_baseline_file", "")), "figma_baseline_file")
    baseline_payload = _read_json_file(baseline_file)
    target_height = float(
        arguments.get(
            "image_target_height",
            baseline_payload.get("expected_image_height", 120),
        )
    )
    node_pattern = str(arguments.get("image_node_pattern", "Image|Preview")).strip() or "Image|Preview"
    scene_file = _resolve_project_file(project_root, str(arguments.get("scene_file", "")), "scenes/main_scene_example.tscn")
    uniform_plan: dict[str, Any] = {"target_height": target_height, "matched_nodes": [], "adjustments": []}
    if scene_file.exists():
        uniform_plan = _build_uniform_height_plan(scene_file, target_height, node_pattern)
    suggestions: list[dict[str, Any]] = []
    layout = compare_payload.get("layout_diff", {})
    if isinstance(layout, dict) and layout.get("dimension_mismatch"):
        suggestions.append(
            {
                "file": "scenes/main_scene_example.tscn",
                "reason": "scene root dimension differs from figma baseline",
                "figma_expected": {"width": layout.get("expected_width"), "height": layout.get("expected_height")},
                "game_actual": {"width": layout.get("actual_width"), "height": layout.get("actual_height")},
                "proposed_change": "adjust root control anchors/size to match figma frame dimensions",
                "confidence": 0.72,
                "risk": "medium",
            }
        )
    visual = compare_payload.get("visual_diff", {})
    if isinstance(visual, dict) and float(visual.get("pixel_diff_ratio", 0.0)) > float(visual.get("pixel_threshold", 0.03)):
        suggestions.append(
            {
                "file": str(scene_file),
                "reason": "visual diff exceeds threshold",
                "figma_expected": {"pixel_diff_ratio_max": visual.get("pixel_threshold")},
                "game_actual": {"pixel_diff_ratio": visual.get("pixel_diff_ratio")},
                "proposed_change": "align spacing/font/color tokens with figma design context",
                "confidence": 0.64,
                "risk": "low",
            }
        )
        if uniform_plan.get("adjustments"):
            suggestions.append(
                {
                    "file": str(scene_file),
                    "reason": "image size drift can be reduced by uniform scaling to target height",
                    "figma_expected": {"image_height": target_height},
                    "game_actual": {
                        "matched_nodes": uniform_plan.get("matched_nodes", []),
                        "first_old_height": (
                            uniform_plan.get("adjustments", [{}])[0].get("old_size", {}).get("height")
                            if uniform_plan.get("adjustments")
                            else None
                        ),
                    },
                    "proposed_change": "apply uniform scaling to matched image nodes so rendered height equals target",
                    "uniform_scale_plan": uniform_plan,
                    "confidence": 0.86,
                    "risk": "low",
                }
            )
    max_suggestions = int(arguments.get("max_suggestions", 10))
    if max_suggestions <= 0:
        max_suggestions = 1
    suggestions = suggestions[:max_suggestions]
    run_id = _slugify(str(compare_payload.get("run_id", "last")))
    payload = {
        "tool": "suggest_ui_fix_patch",
        "generated_at": _utc_iso(),
        "project_root": str(project_root),
        "run_id": compare_payload.get("run_id"),
        "compare_report_file": str(resolved_compare_report),
        "approval_file": str(approval_file),
        "uniform_scale_plan": uniform_plan,
        "suggestions": suggestions,
        "suggestion_count": len(suggestions),
    }
    suggestion_file = _exp_runtime_dir(project_root, cfg) / f"ui_fix_suggestions_{run_id}.json"
    _write_text(suggestion_file, json.dumps(payload, ensure_ascii=False, indent=2))
    return {
        "status": "suggested",
        "project_root": str(project_root),
        "suggestion_file": str(suggestion_file),
        "run_id": compare_payload.get("run_id"),
        "suggestion_count": len(suggestions),
    }


def _tool_get_adapter_contract(ctx: ServerCtx, _arguments: dict[str, Any]) -> dict[str, Any]:
    contract_path = ctx.repo_root / "mcp" / "adapter_contract_v1.json"
    if not contract_path.exists():
        raise AppError("CONTRACT_NOT_FOUND", f"adapter contract file not found: {contract_path}")
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError("CONTRACT_INVALID", "adapter contract json invalid", {"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise AppError("CONTRACT_INVALID", "adapter contract must be JSON object")
    payload["source_file"] = str(contract_path)
    return payload


def _tool_init_project_context(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    return _run_project_context_generation(ctx, arguments, mode="initialized")


def _tool_refresh_project_context(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    return _run_project_context_generation(ctx, arguments, mode="refreshed")


def _tool_get_mcp_runtime_info(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    cfg = _resolve_runtime_config(ctx, arguments)
    project_root_raw = str(arguments.get("project_root", "")).strip()
    project_root = Path(project_root_raw).resolve() if project_root_raw else None
    exp_runtime_info: dict[str, Any] = {"exp_runtime_dir_rel": f"{cfg.exp_dir_rel}/runtime"}
    legacy_hints: list[dict[str, str]] = []
    if project_root is not None and project_root.exists():
        exp_runtime_info = {
            "exp_output_dir": str((project_root / cfg.exp_dir_rel).resolve()),
            "exp_runtime_dir": str(_exp_runtime_dir(project_root, cfg)),
            "exp_runtime_dir_rel": f"{cfg.exp_dir_rel}/runtime",
        }
        legacy_hints = _legacy_layout_hints(project_root)
    return {
        "server_name": cfg.server_name,
        "server_version": cfg.server_version,
        "repo_root": str(ctx.repo_root),
        "plugin_template_dir": str(cfg.plugin_template_dir),
        "workspace_output_dir": DEFAULT_WORKSPACE_DIR_REL,
        "context_output_dir": cfg.context_dir_rel,
        "seed_flow_output_dir": cfg.seed_flow_dir_rel,
        "report_output_dir": cfg.report_dir_rel,
        "exp_output_dir": cfg.exp_dir_rel,
        "exp_runtime": exp_runtime_info,
        "config_sources": cfg.config_sources,
        "legacy_layout_hints": legacy_hints,
        "tool_capabilities": {
            "run_game_basic_test_flow": {
                "implemented": True,
                "status": "implemented",
                "phase": "runtime_gate_and_virtual_input",
                "strict_runtime_required": True,
                "shell_step_output_required": True,
            }
        },
        "tools": [
            "get_mcp_runtime_info",
            "get_adapter_contract",
            "get_basic_test_flow_reference_guide",
            "route_nl_intent",
            "install_godot_plugin",
            "enable_godot_plugin",
            "update_godot_plugin",
            "check_plugin_status",
            "init_project_context",
            "refresh_project_context",
            "generate_flow_seed",
            "design_game_basic_test_flow",
            "update_game_basic_design_flow_by_current_state",
            "figma_design_to_baseline",
            "compare_figma_game_ui",
            "annotate_ui_mismatch",
            "approve_ui_fix_plan",
            "suggest_ui_fix_patch",
            "run_game_basic_test_flow",
            "run_game_basic_test_flow_by_current_state",
            "run_basic_test_flow_orchestrated",
            "auto_fix_game_bug",
        ]
        + sorted(_LEGACY_GAMEPLAYFLOW_TOOL_NAMES),
    }


_LEGACY_MCP_DIR = Path(__file__).resolve().parents[1] / "tools" / "game-test-runner" / "mcp"
_legacy_gameplayflow_mcp_class: type[Any] | None = None
_legacy_gameplayflow_servers: dict[Path, Any] = {}


def _legacy_gtr_mcp_class() -> type[Any]:
    global _legacy_gameplayflow_mcp_class
    if _legacy_gameplayflow_mcp_class is not None:
        return _legacy_gameplayflow_mcp_class
    leg = str(_LEGACY_MCP_DIR.resolve())
    if leg not in sys.path:
        sys.path.insert(0, leg)
    import importlib.util

    spec = importlib.util.spec_from_file_location("pointer_gpf_legacy_gtr_mcp", _LEGACY_MCP_DIR / "server.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load legacy gameplayflow MCP module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cls = getattr(mod, "GameTestMcpServer", None)
    if cls is None:
        raise RuntimeError("GameTestMcpServer missing in legacy gameplayflow MCP module")
    _legacy_gameplayflow_mcp_class = cls
    return cls


def _get_legacy_gameplayflow_server(repo_root: Path) -> Any:
    key = repo_root.resolve()
    cached = _legacy_gameplayflow_servers.get(key)
    if cached is not None:
        return cached
    server = _legacy_gtr_mcp_class()(default_project_root=key)
    _legacy_gameplayflow_servers[key] = server
    return server


def _legacy_gameplayflow_tool_handler(tool_name: str):
    def _handler(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return _get_legacy_gameplayflow_server(ctx.repo_root).invoke(tool_name, arguments)
        except Exception as exc:
            # game-test-runner MCP 使用独立的 AppError 类型；CLI/stdio 仅识别本模块的 AppError。
            as_dict_fn = getattr(exc, "as_dict", None)
            if callable(as_dict_fn):
                try:
                    payload = as_dict_fn()
                except Exception:
                    payload = None
                if isinstance(payload, dict) and "code" in payload and "message" in payload:
                    det = payload.get("details")
                    details = det if isinstance(det, dict) else {}
                    raise AppError(str(payload["code"]), str(payload["message"]), details) from exc
            raise

    return _handler


def _build_legacy_bridge_tool_map() -> dict[str, Any]:
    return {name: _legacy_gameplayflow_tool_handler(name) for name in _LEGACY_GAMEPLAYFLOW_TOOL_NAMES}


def _legacy_gameplayflow_tool_specs(base_props: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": dict(base_props),
        "additionalProperties": True,
    }
    desc = "Legacy gameplayflow tool (game-test-runner MCP compatibility layer)."
    return {
        name: {"description": f"{desc} Original tool name: {name}.", "inputSchema": schema}
        for name in sorted(_LEGACY_GAMEPLAYFLOW_TOOL_NAMES)
    }


def _build_tool_map() -> dict[str, Any]:
    tools: dict[str, Any] = {
        "get_mcp_runtime_info": _tool_get_mcp_runtime_info,
        "get_adapter_contract": _tool_get_adapter_contract,
        "get_basic_test_flow_reference_guide": _tool_get_basic_test_flow_reference_guide,
        "route_nl_intent": _tool_route_nl_intent,
        "install_godot_plugin": _tool_install_godot_plugin,
        "enable_godot_plugin": _tool_enable_godot_plugin,
        "update_godot_plugin": _tool_update_godot_plugin,
        "check_plugin_status": _tool_check_plugin_status,
        "init_project_context": _tool_init_project_context,
        "refresh_project_context": _tool_refresh_project_context,
        "generate_flow_seed": _tool_generate_flow_seed,
        "design_game_basic_test_flow": _tool_design_game_basic_test_flow,
        "update_game_basic_design_flow_by_current_state": _tool_update_game_basic_design_flow_by_current_state,
        "figma_design_to_baseline": _tool_figma_design_to_baseline,
        "compare_figma_game_ui": _tool_compare_figma_game_ui,
        "annotate_ui_mismatch": _tool_annotate_ui_mismatch,
        "approve_ui_fix_plan": _tool_approve_ui_fix_plan,
        "suggest_ui_fix_patch": _tool_suggest_ui_fix_patch,
        "run_game_basic_test_flow": _tool_run_game_basic_test_flow,
        "run_game_basic_test_flow_by_current_state": _tool_run_game_basic_test_flow_by_current_state,
        "run_basic_test_flow_orchestrated": _tool_run_basic_test_flow_orchestrated,
        "auto_fix_game_bug": _tool_auto_fix_game_bug,
    }
    tools.update(_build_legacy_bridge_tool_map())
    return tools


def _build_tool_specs() -> dict[str, dict[str, Any]]:
    base_props: dict[str, Any] = {
        "project_root": {"type": "string", "description": "Absolute path to target Godot project root."},
        "config_file": {"type": "string", "description": "Optional runtime config JSON file path."},
    }
    specs: dict[str, dict[str, Any]] = {
        "get_mcp_runtime_info": {
            "description": "Get runtime and tool metadata for PointerGPF MCP.",
            "inputSchema": {
                "type": "object",
                "properties": {"config_file": base_props["config_file"], "project_root": base_props["project_root"]},
            },
        },
        "get_adapter_contract": {
            "description": "Return adapter contract JSON for Godot integration.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        "route_nl_intent": {
            "description": (
                "Route natural-language command text to MCP tool intents. "
                "Result includes canonical_example_project_root / canonical_example_project_rel "
                "for this repo's MCP dev sample (examples/godot_minimal)."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["text"],
                "properties": {
                    "text": {"type": "string", "description": "Natural-language command text."},
                },
            },
        },
        "get_basic_test_flow_reference_guide": {
            "description": (
                "Return markdown for basic test flow reference usage and natural-language triggers "
                "(docs/mcp-basic-test-flow-reference-usage.md). "
                "Users can say e.g. '基础测试流程怎么用' and route_nl_intent will target this tool."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    **base_props,
                },
            },
        },
        "install_godot_plugin": {
            "description": "Install PointerGPF plugin files and enable plugin in project.godot.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": dict(base_props),
            },
        },
        "enable_godot_plugin": {
            "description": "Enable existing PointerGPF plugin in project.godot.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": dict(base_props),
            },
        },
        "update_godot_plugin": {
            "description": "Overwrite plugin files and ensure plugin enabled.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": dict(base_props),
            },
        },
        "check_plugin_status": {
            "description": "Check plugin files and plugin enabled status.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": dict(base_props),
            },
        },
        "init_project_context": {
            "description": "Initialize project context and candidate documents.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "max_files": {"type": "integer", "description": "Maximum files to scan."},
                },
            },
        },
        "refresh_project_context": {
            "description": "Refresh project context incrementally.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "max_files": {"type": "integer", "description": "Maximum files to scan."},
                },
            },
        },
        "generate_flow_seed": {
            "description": "Generate flow seed JSON from context index.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "flow_id": {"type": "string"},
                    "flow_name": {"type": "string"},
                    "output_file": {"type": "string"},
                    "strategy": {"type": "string", "enum": ["auto", "ui", "exploration", "builder", "generic"]},
                },
            },
        },
        "design_game_basic_test_flow": {
            "description": (
                "Natural-language trigger command: '设计游戏基础测试流程'. "
                "Generate a basic game smoke test flow that covers open/enter game, save-load if available, and simple implemented feature checks. "
                "Agents should consult `project_context/04-flow-authoring-guide.md` (game-type expectations) and PointerGPF `docs/mcp-basic-test-flow-game-type-expectations.md` when refining steps for fuller/faster gameplay coverage."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "flow_id": {"type": "string"},
                    "flow_name": {"type": "string"},
                    "output_file": {"type": "string"},
                    "max_feature_checks": {"type": "integer"},
                    "strategy": {"type": "string", "enum": ["auto", "ui", "exploration", "builder", "generic"]},
                    "allow_low_likelihood": {
                        "type": "boolean",
                        "description": "If true, keep static player_click_likelihood=none/low candidates when ordering.",
                    },
                },
            },
        },
        "update_game_basic_design_flow_by_current_state": {
            "description": (
                "Natural-language trigger command: '根据游戏当前状态,更新设计游戏基础设计流程'. "
                "Refresh project context first, then regenerate the basic game smoke test flow using latest game state."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "flow_id": {"type": "string"},
                    "flow_name": {"type": "string"},
                    "output_file": {"type": "string"},
                    "max_files": {"type": "integer", "description": "Maximum files to scan during refresh."},
                    "max_feature_checks": {"type": "integer"},
                    "strategy": {"type": "string", "enum": ["auto", "ui", "exploration", "builder", "generic"]},
                    "allow_low_likelihood": {
                        "type": "boolean",
                        "description": "If true, keep static player_click_likelihood=none/low candidates when ordering.",
                    },
                },
            },
        },
        "run_game_basic_test_flow": {
            "description": (
                "Run a basic gameplay flow test via file bridge (command.json/response.json) with three-phase event reporting. "
                "Strict policy is always enforced: play_mode runtime gate required + per-step shell output."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "flow_id": {"type": "string", "description": "Logical flow identifier when not using flow_file."},
                    "flow_file": {"type": "string", "description": "Path to flow JSON file."},
                    "step_timeout_ms": {"type": "integer", "description": "Per-step timeout in milliseconds."},
                    "fail_fast": {"type": "boolean", "description": "Stop on first step failure."},
                    "shell_report": {
                        "type": "boolean",
                        "description": "Compatibility field. Runtime always enforces shell step output.",
                    },
                    "require_play_mode": {
                        "type": "boolean",
                        "description": "Compatibility field. Runtime always enforces play mode gate.",
                    },
                    "observe_engine_errors": {
                        "type": "boolean",
                        "description": "If true (default), poll pointer_gpf/tmp/runtime_diagnostics.json while waiting for bridge and fail fast on severity error/fatal.",
                    },
                    "close_project_on_finish": {
                        "type": "boolean",
                        "description": "If true (default), request closeProject after the run (stop Play, keep editor).",
                    },
                    "force_terminate_godot_on_flow_failure": {
                        "type": "boolean",
                        "description": (
                            "If true, after a failed flow when closeProject is not acknowledged, attempt to terminate "
                            "Godot OS processes whose command line contains project_root (may kill the editor). "
                            "Default false; see docs/design/99-tools/14-mcp-core-invariants.md."
                        ),
                    },
                    "godot_executable": {"type": "string", "description": "Optional path to Godot editor binary for auto-launch."},
                    "godot_editor_executable": {"type": "string", "description": "Alias for godot_executable."},
                    "godot_path": {"type": "string", "description": "Alias for godot_executable."},
                    "auto_repair": {
                        "type": "boolean",
                        "description": (
                            "If true (default unless env GPF_AUTO_REPAIR_DEFAULT=0), on failure chain auto_fix_game_bug "
                            "and re-run up to max_repair_rounds. CI often sets false explicitly."
                        ),
                    },
                    "max_repair_rounds": {
                        "type": "integer",
                        "description": "When auto_repair: outer flow+fix rounds, 1–8. Default 2.",
                    },
                    "auto_fix_max_cycles": {
                        "type": "integer",
                        "description": "When auto_repair: max_cycles passed to auto_fix_game_bug each round. Default 3; 0 skips fix.",
                    },
                    "agent_session_defaults": {
                        "type": "boolean",
                        "description": (
                            "When true and auto_repair is omitted, force auto_repair default on even if env "
                            "GPF_AUTO_REPAIR_DEFAULT=0 (AI agent / IDE sessions). CI must not set this. "
                            "Same effect as env GPF_AGENT_SESSION_DEFAULTS=1."
                        ),
                    },
                },
            },
        },
        "run_game_basic_test_flow_by_current_state": {
            "description": (
                "Refresh project context, regenerate the basic game test flow from current state, then run it via the file bridge. "
                "Combines update_game_basic_design_flow_by_current_state and run_game_basic_test_flow using the generated flow_file. "
                "Same auto_repair / max_repair_rounds / auto_fix_max_cycles semantics as run_game_basic_test_flow."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "flow_id": {"type": "string", "description": "Logical flow identifier when not using flow_file."},
                    "flow_file": {"type": "string", "description": "Path to flow JSON file; normally taken from regenerated flow_result."},
                    "step_timeout_ms": {"type": "integer", "description": "Per-step timeout in milliseconds."},
                    "fail_fast": {"type": "boolean", "description": "Stop on first step failure."},
                    "shell_report": {
                        "type": "boolean",
                        "description": "Compatibility field. Runtime always enforces shell step output.",
                    },
                    "require_play_mode": {
                        "type": "boolean",
                        "description": "Compatibility field. Runtime always enforces play mode gate and step shell output.",
                    },
                    "observe_engine_errors": {
                        "type": "boolean",
                        "description": "Forwarded to run_game_basic_test_flow: poll runtime_diagnostics.json while waiting for bridge.",
                    },
                    "close_project_on_finish": {
                        "type": "boolean",
                        "description": "Forwarded to run_game_basic_test_flow.",
                    },
                    "force_terminate_godot_on_flow_failure": {
                        "type": "boolean",
                        "description": "Forwarded to run_game_basic_test_flow.",
                    },
                    "godot_executable": {"type": "string"},
                    "godot_editor_executable": {"type": "string"},
                    "godot_path": {"type": "string"},
                    "auto_repair": {
                        "type": "boolean",
                        "description": "Same as run_game_basic_test_flow; forwarded to inner run after refresh.",
                    },
                    "max_repair_rounds": {"type": "integer", "description": "Same as run_game_basic_test_flow."},
                    "auto_fix_max_cycles": {"type": "integer", "description": "Same as run_game_basic_test_flow."},
                    "agent_session_defaults": {
                        "type": "boolean",
                        "description": "Same as run_game_basic_test_flow.",
                    },
                },
            },
        },
        "run_basic_test_flow_orchestrated": {
            "description": (
                "Legacy explicit-opt-in entry: maps to run_game_basic_test_flow_by_current_state with "
                "auto_repair=true, max_repair_rounds=max_orchestration_rounds, auto_fix_max_cycles as passed. "
                "Prefer calling run_game_basic_test_flow_by_current_state directly with those fields; "
                "orchestration_explicit_opt_in=true still required for this tool name."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "orchestration_explicit_opt_in"],
                "properties": {
                    **base_props,
                    "orchestration_explicit_opt_in": {
                        "type": "boolean",
                        "description": "Must be true to run; prevents accidental expensive chained calls.",
                    },
                    "max_orchestration_rounds": {
                        "type": "integer",
                        "description": "Flow+fix cycles (1–8). Default 2.",
                    },
                    "auto_fix_max_cycles": {
                        "type": "integer",
                        "description": "max_cycles passed to auto_fix_game_bug each round. Default 3.",
                    },
                    "flow_id": {"type": "string"},
                    "flow_file": {"type": "string"},
                    "step_timeout_ms": {"type": "integer"},
                    "fail_fast": {"type": "boolean"},
                    "observe_engine_errors": {"type": "boolean"},
                    "close_project_on_finish": {"type": "boolean"},
                    "force_terminate_godot_on_flow_failure": {"type": "boolean"},
                    "godot_executable": {"type": "string"},
                    "godot_editor_executable": {"type": "string"},
                    "godot_path": {"type": "string"},
                },
            },
        },
        "auto_fix_game_bug": {
            "description": "Run verify -> diagnose -> patch -> retest loop for gameplay bugs.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "issue"],
                "properties": {
                    **base_props,
                    "issue": {"type": "string", "description": "User-reported gameplay bug description."},
                    "max_cycles": {"type": "integer", "description": "Maximum fix cycles."},
                    "timeout_seconds": {"type": "number", "description": "Wall-clock timeout for the whole loop."},
                    "flow_id": {"type": "string", "description": "Optional flow id for verification runs."},
                    "step_timeout_ms": {"type": "integer", "description": "Per-step timeout for verification flow."},
                    "shell_report": {"type": "boolean", "description": "Enable readable shell broadcasts in verification."},
                },
            },
        },
        "figma_design_to_baseline": {
            "description": "Persist Figma design context and screenshot as baseline artifact.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "figma_file_key", "figma_node_id", "figma_screenshot_file"],
                "properties": {
                    **base_props,
                    "figma_file_key": {"type": "string"},
                    "figma_node_id": {"type": "string"},
                    "figma_version": {"type": "string"},
                    "figma_screenshot_file": {"type": "string"},
                    "figma_design_context": {"type": "object"},
                    "image_target_height": {"type": "number"},
                },
            },
        },
        "compare_figma_game_ui": {
            "description": "Compare Figma baseline screenshot/context against game UI screenshot.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "figma_baseline_file", "game_snapshot_file"],
                "properties": {
                    **base_props,
                    "figma_baseline_file": {"type": "string"},
                    "game_snapshot_file": {"type": "string"},
                    "pixel_threshold": {"type": "number"},
                    "perceptual_threshold": {"type": "number"},
                    "resize_to_baseline": {"type": "boolean"},
                    "report_basename": {"type": "string"},
                },
            },
        },
        "annotate_ui_mismatch": {
            "description": "Generate mismatch annotation report from compare result.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "compare_report_file"],
                "properties": {
                    **base_props,
                    "compare_report_file": {"type": "string"},
                },
            },
        },
        "approve_ui_fix_plan": {
            "description": "Record approval gate result for UI fix suggestions.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "compare_report_file", "approved"],
                "properties": {
                    **base_props,
                    "compare_report_file": {"type": "string"},
                    "approved": {"type": "boolean"},
                    "approval_token": {"type": "string"},
                },
            },
        },
        "suggest_ui_fix_patch": {
            "description": "Generate UI fix suggestion patch draft from compare report.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "compare_report_file", "approval_file"],
                "properties": {
                    **base_props,
                    "compare_report_file": {"type": "string"},
                    "approval_file": {"type": "string"},
                    "max_suggestions": {"type": "integer"},
                    "scene_file": {"type": "string"},
                    "image_target_height": {"type": "number"},
                    "image_node_pattern": {"type": "string"},
                },
            },
        },
    }
    specs.update(_legacy_gameplayflow_tool_specs(base_props))
    return specs


def _stdio_framing_error() -> None:
    global _stdio_soft_errors
    _stdio_soft_errors += 1
    if _stdio_soft_errors >= _STDIO_SOFT_ERROR_CAP:
        print("MCP stdio: too many consecutive parse/framing errors", file=sys.stderr)
        sys.exit(2)


def _stdio_framing_ok() -> None:
    global _stdio_soft_errors
    _stdio_soft_errors = 0


def _read_mcp_message() -> dict[str, Any] | None:
    global _MCP_IO_MODE
    # Be lenient on transport framing:
    # 1) Standard MCP stdio headers (Content-Length)
    # 2) JSON lines (some clients/proxies write one JSON object per line)
    while True:
        first = sys.stdin.buffer.readline()
        if not first:
            return None
        if first in (b"\r\n", b"\n"):
            continue

        first_text = first.decode("utf-8", errors="replace").strip()
        if first_text.startswith("{"):
            try:
                payload = json.loads(first_text)
            except json.JSONDecodeError:
                _stdio_framing_error()
                continue
            if isinstance(payload, dict):
                _MCP_IO_MODE = "jsonl"
                _stdio_framing_ok()
                return payload
            _stdio_framing_error()
            continue

        headers: dict[str, str] = {}
        if ":" in first_text:
            key, value = first_text.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text or ":" not in text:
                continue
            key, value = text.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        content_length_raw = headers.get("content-length", "")
        if not content_length_raw:
            _stdio_framing_error()
            continue
        try:
            content_length = int(content_length_raw)
        except ValueError:
            _stdio_framing_error()
            continue
        body = sys.stdin.buffer.read(content_length)
        if not body:
            _stdio_framing_error()
            continue
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            _stdio_framing_error()
            continue
        if isinstance(payload, dict):
            _MCP_IO_MODE = "header"
            _stdio_framing_ok()
            return payload
        _stdio_framing_error()


def _write_mcp_message(payload: dict[str, Any]) -> None:
    body_text = json.dumps(payload, ensure_ascii=False)
    if _MCP_IO_MODE == "jsonl":
        sys.stdout.buffer.write((body_text + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
        return
    body = body_text.encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _mcp_jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _mcp_jsonrpc_error(request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _run_stdio_mcp(ctx: ServerCtx, tool_map: dict[str, Any], startup_config_file: str | None = None) -> int:
    tool_specs = _build_tool_specs()
    stdio_server_version = _default_runtime_config(ctx).server_version
    while True:
        req = _read_mcp_message()
        if req is None:
            return 0
        request_id = req.get("id")
        method = str(req.get("method", "")).strip()
        params = req.get("params", {})
        if not isinstance(params, dict):
            params = {}
        is_notification = "id" not in req
        try:
            if method == "initialize":
                if is_notification:
                    continue
                _write_mcp_message(
                    _mcp_jsonrpc_result(
                        request_id,
                        {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": DEFAULT_SERVER_NAME, "version": stdio_server_version},
                        },
                    )
                )
                continue
            if method == "notifications/initialized":
                continue
            if method == "ping":
                if not is_notification:
                    _write_mcp_message(_mcp_jsonrpc_result(request_id, {}))
                continue
            if method == "tools/list":
                if is_notification:
                    continue
                tools = [
                    {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
                    for name, spec in tool_specs.items()
                ]
                _write_mcp_message(_mcp_jsonrpc_result(request_id, {"tools": tools}))
                continue
            if method == "tools/call":
                if is_notification:
                    continue
                tool_name = str(params.get("name", "")).strip()
                args_payload = params.get("arguments", {})
                if not isinstance(args_payload, dict):
                    raise AppError("INVALID_ARGUMENT", "tool arguments must be an object")
                if startup_config_file and "config_file" not in args_payload:
                    args_payload["config_file"] = startup_config_file
                handler = tool_map.get(tool_name)
                if handler is None:
                    raise AppError("UNSUPPORTED_TOOL", f"unsupported tool: {tool_name}")
                result = handler(ctx, args_payload)
                _write_mcp_message(
                    _mcp_jsonrpc_result(
                        request_id,
                        {
                            "structuredContent": result,
                            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                        },
                    )
                )
                continue
            if is_notification:
                continue
            _write_mcp_message(_mcp_jsonrpc_error(request_id, -32601, f"Method not found: {method}"))
        except AppError as exc:
            if not is_notification:
                _write_mcp_message(_mcp_jsonrpc_error(request_id, -32000, exc.message, exc.as_dict()))
        except Exception as exc:  # pylint: disable=broad-except
            if not is_notification:
                _write_mcp_message(_mcp_jsonrpc_error(request_id, -32603, "Internal error", {"error": str(exc)}))


def _run_cli_mode(args: argparse.Namespace, ctx: ServerCtx, tool_map: dict[str, Any]) -> int:
    if not args.tool:
        raise AppError("INVALID_ARGUMENT", "--tool is required in CLI mode")
    payload = json.loads(args.args)
    if not isinstance(payload, dict):
        raise AppError("INVALID_ARGUMENT", "args must be a JSON object")
    if args.project_root is not None:
        payload["project_root"] = args.project_root
    if args.config_file is not None:
        payload["config_file"] = args.config_file
    if args.max_files is not None:
        payload["max_files"] = int(args.max_files)
    if args.flow_id is not None:
        payload["flow_id"] = args.flow_id
    if args.flow_name is not None:
        payload["flow_name"] = args.flow_name
    if args.output_file is not None:
        payload["output_file"] = args.output_file
    if args.strategy is not None:
        payload["strategy"] = args.strategy
    if getattr(args, "allow_low_likelihood", False):
        payload["allow_low_likelihood"] = True
    handler = tool_map.get(args.tool)
    if handler is None:
        raise AppError("UNSUPPORTED_TOOL", f"unsupported tool: {args.tool}")
    result = handler(ctx, payload)
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PointerGPF MCP server")
    parser.add_argument("--tool", required=False, help="Tool name for CLI compatibility mode")
    parser.add_argument("--stdio", action="store_true", help="Force stdio MCP server mode")
    parser.add_argument("--args", default="{}", help="JSON args object")
    parser.add_argument("--config-file", default=None, help="Explicit runtime config JSON file path")
    parser.add_argument("--project-root", default=None, help="Shortcut for project_root")
    parser.add_argument("--max-files", type=int, default=None, help="Shortcut for max_files")
    parser.add_argument("--flow-id", default=None, help="Shortcut for flow_id")
    parser.add_argument("--flow-name", default=None, help="Shortcut for flow_name")
    parser.add_argument("--output-file", default=None, help="Shortcut for output_file")
    parser.add_argument("--strategy", default=None, help="Shortcut for seed strategy (auto/ui/exploration/builder/generic)")
    parser.add_argument(
        "--allow-low-likelihood",
        action="store_true",
        help="For design_game_basic_test_flow: include static low/none click-likelihood candidates when ranking.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    ctx = ServerCtx(
        repo_root=repo_root,
        template_plugin_dir=repo_root / "godot_plugin_template" / "addons" / DEFAULT_PLUGIN_ID,
    )
    tool_map = _build_tool_map()
    try:
        if args.stdio or not args.tool:
            return _run_stdio_mcp(ctx, tool_map, startup_config_file=args.config_file)
        return _run_cli_mode(args, ctx, tool_map)
    except AppError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        print(json.dumps({"ok": False, "error": {"code": "INTERNAL_ERROR", "message": str(exc)}}, ensure_ascii=False))
        return 1


def _remediation_handler_runtime_gate(
    ctx: ServerCtx, project_root: Path, tool_args: dict[str, Any], details: dict[str, Any]
) -> dict[str, Any]:
    _ = details
    meta, boot = _ensure_runtime_play_mode(project_root, tool_args)
    ok = bool(meta.get("runtime_gate_passed"))
    out: dict[str, Any] = {
        "handled": ok,
        "actions": [{"kind": "bootstrap_runtime", "runtime_gate_passed": ok}],
        "notes": "retried play-mode bootstrap via _ensure_runtime_play_mode",
        "engine_bootstrap": boot,
    }
    if ok:
        out["runtime_meta"] = meta
    return out


def _remediation_handler_flow_generation_blocked(
    ctx: ServerCtx, project_root: Path, tool_args: dict[str, Any], details: dict[str, Any]
) -> dict[str, Any]:
    _ = details
    rargs = {**tool_args, "project_root": str(project_root)}
    rargs.setdefault("max_files", 400)
    try:
        refresh_out = _tool_refresh_project_context(ctx, rargs)
    except AppError as exc:
        return {
            "handled": False,
            "actions": [],
            "notes": str(exc.message),
            "error": exc.as_dict(),
        }
    try:
        upd = _tool_update_game_basic_design_flow_by_current_state(
            ctx, {**tool_args, "project_root": str(project_root)}
        )
    except AppError as exc:
        return {
            "handled": False,
            "actions": [{"kind": "refresh_project_context", "summary": str(refresh_out.get("status", ""))}],
            "notes": str(exc.message),
            "error": exc.as_dict(),
        }
    fr = upd.get("flow_result") if isinstance(upd.get("flow_result"), dict) else {}
    blocked = str(fr.get("status", "")).strip() == "blocked"
    return {
        "handled": not blocked,
        "actions": [
            {"kind": "refresh_project_context", "summary": str(refresh_out.get("status", ""))},
            {"kind": "regenerated_flow_probe", "blocked": blocked},
        ],
        "notes": "context refreshed; flow gate still blocked" if blocked else "context refreshed; flow gate open",
        "flow_result": fr,
    }


def _register_default_remediation_handlers() -> None:
    remediation_handlers.register_handler("runtime_gate", _remediation_handler_runtime_gate)
    remediation_handlers.register_handler("flow_generation_blocked", _remediation_handler_flow_generation_blocked)


_register_default_remediation_handlers()


if __name__ == "__main__":
    raise SystemExit(main())
