from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import Any


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if str(_repo_root()) not in sys.path:
    sys.path.insert(0, str(_repo_root()))


def _hidden_run(cmd: list[str], *, cwd: Path, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(cmd, **kwargs)


def _list_project_processes(project_root: Path) -> list[dict[str, Any]]:
    probe = (
        "$target = '{target}'; "
        "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object {{ $_.Name -like 'Godot*.exe' -and $_.CommandLine -match [regex]::Escape($target) }} | "
        "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    ).format(target=str(project_root.resolve()))
    proc = _hidden_run(["powershell", "-Command", probe], cwd=_repo_root(), timeout=30)
    raw = proc.stdout.strip()
    if not raw:
        return []
    payload = json.loads(raw)
    if isinstance(payload, dict):
        payload = [payload]
    return payload if isinstance(payload, list) else []


def _kill_project_processes(project_root: Path) -> None:
    for item in _list_project_processes(project_root):
        pid = int(item.get("ProcessId", -1))
        if pid > 0:
            try:
                _hidden_run(["taskkill", "/PID", str(pid), "/T", "/F"], cwd=_repo_root(), timeout=30)
            except Exception:
                pass
    time.sleep(2)


def _clear_runtime_markers(project_root: Path) -> None:
    tmp_dir = project_root / "pointer_gpf" / "tmp"
    for name in (
        "flow_run.lock",
        "runtime_gate.json",
        "runtime_session.json",
        "runtime_diagnostics.json",
        "command.json",
        "response.json",
        "auto_enter_play_mode.flag",
        "auto_stop_play_mode.flag",
    ):
        (tmp_dir / name).unlink(missing_ok=True)


def _reset_runtime_state(project_root: Path) -> None:
    _kill_project_processes(project_root)
    _clear_runtime_markers(project_root)


def _load_test_suite(paths: list[Path]) -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    for idx, path in enumerate(paths):
        spec = importlib.util.spec_from_file_location(f"v2_regression_{idx}", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"unable to load test module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


def run_v2_unit_tests() -> dict[str, Any]:
    repo = _repo_root()
    paths = [
        repo / "v2" / "tests" / "test_basicflow_assets.py",
        repo / "v2" / "tests" / "test_basicflow_staleness.py",
        repo / "v2" / "tests" / "test_basicflow_analysis.py",
        repo / "v2" / "tests" / "test_basicflow_generation.py",
        repo / "v2" / "tests" / "test_basicflow_generation_session.py",
        repo / "v2" / "tests" / "test_server.py",
        repo / "v2" / "tests" / "test_windows_isolated_runtime.py",
        repo / "v2" / "tests" / "test_flow_runner.py",
        repo / "v2" / "tests" / "test_preflight.py",
        repo / "v2" / "tests" / "test_plugin_sync.py",
    ]
    suite = _load_test_suite(paths)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "name": "v2_unit_tests",
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
    }


def run_preflight(project_root: Path) -> dict[str, Any]:
    proc = _hidden_run(
        [sys.executable, "-m", "v2.mcp_core.server", "--tool", "preflight_project", "--project-root", str(project_root)],
        cwd=_repo_root(),
        timeout=120,
    )
    payload = json.loads(proc.stdout)
    return {
        "name": "preflight_project",
        "ok": proc.returncode == 0 and bool(payload.get("ok")) and bool(payload.get("result", {}).get("ok")),
        "returncode": proc.returncode,
        "payload": payload,
    }


def run_interactive_flow(project_root: Path) -> dict[str, Any]:
    _reset_runtime_state(project_root)
    flow_file = _repo_root() / "v2" / "flows" / "basic_interactive_flow.json"
    proc = _hidden_run(
        [
            sys.executable,
            "-m",
            "v2.mcp_core.server",
            "--tool",
            "run_basic_flow",
            "--project-root",
            str(project_root),
            "--flow-file",
            str(flow_file),
        ],
        cwd=_repo_root(),
        timeout=240,
    )
    payload = json.loads(proc.stdout)
    result = payload.get("result", {})
    return {
        "name": "basic_interactive_flow",
        "ok": (
            proc.returncode == 0
            and bool(payload.get("ok"))
            and result.get("execution", {}).get("status") == "passed"
            and result.get("project_close", {}).get("status") == "verified"
        ),
        "returncode": proc.returncode,
        "payload": payload,
    }


def _extract_session_id(payload: dict[str, Any]) -> str:
    return str(payload.get("result", {}).get("session_id", "")).strip()


def run_basicflow_session_flow(project_root: Path) -> dict[str, Any]:
    start_proc = _hidden_run(
        [sys.executable, "-m", "v2.mcp_core.server", "--tool", "start_basic_flow_generation_session", "--project-root", str(project_root)],
        cwd=_repo_root(),
        timeout=120,
    )
    start_payload = json.loads(start_proc.stdout)
    session_id = _extract_session_id(start_payload)
    step_payloads: list[dict[str, Any]] = [start_payload]
    if start_proc.returncode != 0 or not start_payload.get("ok") or not session_id:
        return {
            "name": "basicflow_session_flow",
            "ok": False,
            "returncode": start_proc.returncode,
            "payload": {"start": start_payload},
        }

    answers = [
        ("main_scene_is_entry", "true"),
        ("tested_features", "进入主流程,基础操作"),
        ("include_screenshot_evidence", "false"),
    ]
    for question_id, answer in answers:
        proc = _hidden_run(
            [
                sys.executable,
                "-m",
                "v2.mcp_core.server",
                "--tool",
                "answer_basic_flow_generation_session",
                "--project-root",
                str(project_root),
                "--session-id",
                session_id,
                "--question-id",
                question_id,
                "--answer",
                answer,
            ],
            cwd=_repo_root(),
            timeout=120,
        )
        payload = json.loads(proc.stdout)
        step_payloads.append(payload)
        if proc.returncode != 0 or not payload.get("ok"):
            return {
                "name": "basicflow_session_flow",
                "ok": False,
                "returncode": proc.returncode,
                "payload": {"steps": step_payloads},
            }

    complete_proc = _hidden_run(
        [
            sys.executable,
            "-m",
            "v2.mcp_core.server",
            "--tool",
            "complete_basic_flow_generation_session",
            "--project-root",
            str(project_root),
            "--session-id",
            session_id,
        ],
        cwd=_repo_root(),
        timeout=120,
    )
    complete_payload = json.loads(complete_proc.stdout)
    return {
        "name": "basicflow_session_flow",
        "ok": complete_proc.returncode == 0 and bool(complete_payload.get("ok")) and complete_payload.get("result", {}).get("status") == "generated",
        "returncode": complete_proc.returncode,
        "payload": {
            "start": start_payload,
            "answers": step_payloads[1:],
            "complete": complete_payload,
        },
    }


def run_generation_questions(project_root: Path) -> dict[str, Any]:
    proc = _hidden_run(
        [sys.executable, "-m", "v2.mcp_core.server", "--tool", "get_basic_flow_generation_questions", "--project-root", str(project_root)],
        cwd=_repo_root(),
        timeout=120,
    )
    payload = json.loads(proc.stdout)
    result = payload.get("result", {})
    return {
        "name": "basicflow_generation_questions",
        "ok": proc.returncode == 0 and bool(payload.get("ok")) and result.get("status") == "questions_ready" and int(result.get("question_count", 0)) == 3,
        "returncode": proc.returncode,
        "payload": payload,
    }


def run_default_basicflow(project_root: Path) -> dict[str, Any]:
    _reset_runtime_state(project_root)
    proc = _hidden_run(
        [sys.executable, "-m", "v2.mcp_core.server", "--tool", "run_basic_flow", "--project-root", str(project_root)],
        cwd=_repo_root(),
        timeout=240,
    )
    payload = json.loads(proc.stdout)
    result = payload.get("result", {})
    return {
        "name": "default_basicflow",
        "ok": (
            proc.returncode == 0
            and bool(payload.get("ok"))
            and result.get("execution", {}).get("status") == "passed"
            and result.get("project_close", {}).get("status") == "verified"
            and result.get("basicflow", {}).get("used_project_basicflow") is True
        ),
        "returncode": proc.returncode,
        "payload": payload,
    }


def run_basicflow_stale_analysis(project_root: Path) -> dict[str, Any]:
    proc = _hidden_run(
        [sys.executable, "-m", "v2.mcp_core.server", "--tool", "analyze_basic_flow_staleness", "--project-root", str(project_root)],
        cwd=_repo_root(),
        timeout=120,
    )
    payload = json.loads(proc.stdout)
    result = payload.get("result", {})
    return {
        "name": "basicflow_stale_analysis",
        "ok": proc.returncode == 0 and bool(payload.get("ok")) and bool(result.get("status")),
        "returncode": proc.returncode,
        "payload": payload,
    }


def _touch_project_file_for_stale(project_root: Path) -> None:
    project_file = project_root / "project.godot"
    if project_file.is_file():
        project_file.touch()


def run_stale_override_flow(project_root: Path) -> dict[str, Any]:
    _reset_runtime_state(project_root)
    _touch_project_file_for_stale(project_root)
    stale_proc = _hidden_run(
        [sys.executable, "-m", "v2.mcp_core.server", "--tool", "run_basic_flow", "--project-root", str(project_root)],
        cwd=_repo_root(),
        timeout=120,
    )
    stale_payload = json.loads(stale_proc.stdout)
    override_proc = _hidden_run(
        [
            sys.executable,
            "-m",
            "v2.mcp_core.server",
            "--tool",
            "run_basic_flow",
            "--project-root",
            str(project_root),
            "--allow-stale-basicflow",
        ],
        cwd=_repo_root(),
        timeout=240,
    )
    override_payload = json.loads(override_proc.stdout)
    override_result = override_payload.get("result", {})
    return {
        "name": "basicflow_stale_override",
        "ok": (
            stale_proc.returncode != 0
            and stale_payload.get("error", {}).get("code") == "BASICFLOW_STALE"
            and override_proc.returncode == 0
            and bool(override_payload.get("ok"))
            and override_result.get("execution", {}).get("status") == "passed"
            and override_result.get("basicflow", {}).get("status") == "stale"
        ),
        "returncode": override_proc.returncode,
        "payload": {"stale": stale_payload, "override": override_payload},
    }


def run_runtime_guards(project_root: Path) -> dict[str, Any]:
    proc = _hidden_run(
        [
            sys.executable,
            str(_repo_root() / "scripts" / "verify-v2-runtime-guards.py"),
            "--project-root",
            str(project_root),
            "--check",
            "all",
        ],
        cwd=_repo_root(),
        timeout=300,
    )
    payload = json.loads(proc.stdout)
    return {
        "name": "runtime_guards",
        "ok": proc.returncode == 0 and bool(payload.get("ok")),
        "returncode": proc.returncode,
        "payload": payload,
    }


def run_isolated_runtime_flow(project_root: Path, flow_name: str) -> dict[str, Any]:
    _reset_runtime_state(project_root)
    flow_file = _repo_root() / "v2" / "flows" / flow_name
    proc = _hidden_run(
        [
            sys.executable,
            "-m",
            "v2.mcp_core.server",
            "--tool",
            "run_basic_flow",
            "--project-root",
            str(project_root),
            "--flow-file",
            str(flow_file),
            "--execution-mode",
            "isolated_runtime",
        ],
        cwd=_repo_root(),
        timeout=240,
    )
    payload = json.loads(proc.stdout)
    result = payload.get("result", {})
    return {
        "name": f"isolated_runtime_{flow_file.stem}",
        "ok": (
            proc.returncode == 0
            and bool(payload.get("ok"))
            and result.get("execution_mode") == "isolated_runtime"
            and result.get("isolation", {}).get("isolated") is True
            and result.get("isolation", {}).get("status") == "isolated_desktop"
            and result.get("isolation", {}).get("separate_desktop") is True
            and result.get("play_mode", {}).get("status") == "launched_isolated_runtime"
            and result.get("execution", {}).get("status") == "passed"
            and result.get("project_close", {}).get("status") == "verified"
        ),
        "returncode": proc.returncode,
        "payload": payload,
    }


def run_isolated_runtime_host_activity_flow(project_root: Path, flow_name: str) -> dict[str, Any]:
    helper_path = _repo_root() / "scripts" / "verify-v2-isolated-runtime-with-host-activity.py"
    spec = importlib.util.spec_from_file_location("verify_v2_isolated_runtime_with_host_activity", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load host activity helper: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.run_isolated_runtime_flow_with_host_activity(project_root, flow_name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fixed V2 regression bundle.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--include-isolated-runtime", action="store_true")
    parser.add_argument("--include-host-activity", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    try:
        results = [
            run_v2_unit_tests(),
            run_preflight(project_root),
            run_interactive_flow(project_root),
            run_generation_questions(project_root),
            run_basicflow_session_flow(project_root),
            run_default_basicflow(project_root),
            run_basicflow_stale_analysis(project_root),
            run_stale_override_flow(project_root),
            run_runtime_guards(project_root),
        ]
        if args.include_isolated_runtime:
            results.extend(
                [
                    run_isolated_runtime_flow(project_root, "basic_minimal_flow.json"),
                    run_isolated_runtime_flow(project_root, "basic_interactive_flow.json"),
                ]
            )
        if args.include_host_activity:
            results.extend(
                [
                    run_isolated_runtime_host_activity_flow(project_root, "basic_minimal_flow.json"),
                    run_isolated_runtime_host_activity_flow(project_root, "basic_interactive_flow.json"),
                ]
            )
        ok = all(item.get("ok", False) for item in results)
        print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False))
        return 0 if ok else 2
    finally:
        _reset_runtime_state(project_root)


if __name__ == "__main__":
    raise SystemExit(main())
