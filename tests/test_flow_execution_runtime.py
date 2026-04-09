import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


def _run_tool_cli_raw(repo_root: Path, tool: str, args: dict) -> tuple[int, dict]:
    cmd = [
        "python",
        str(repo_root / "mcp" / "server.py"),
        "--tool",
        tool,
        "--args",
        json.dumps(args, ensure_ascii=False),
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


class FlowExecutionToolRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.project_root = self.work / "proj"
        self.project_root.mkdir(parents=True, exist_ok=True)
        (self.project_root / "project.godot").write_text('[application]\nconfig/name="tmp"\n', encoding="utf-8")
        self._write_runtime_gate_marker()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_runtime_gate_marker(
        self,
        runtime_mode: str = "play_mode",
        runtime_entry: str = "already_running_play_session",
        runtime_gate_passed: bool = True,
    ) -> None:
        bridge = self.project_root / "pointer_gpf" / "tmp"
        bridge.mkdir(parents=True, exist_ok=True)
        (bridge / "runtime_gate.json").write_text(
            json.dumps(
                {
                    "runtime_mode": runtime_mode,
                    "runtime_entry": runtime_entry,
                    "runtime_gate_passed": runtime_gate_passed,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_get_mcp_runtime_info_lists_run_game_basic_test_flow(self) -> None:
        code, payload = _run_tool_cli_raw(self.repo_root, "get_mcp_runtime_info", {})
        self.assertEqual(code, 0, msg=f"{payload}")
        self.assertTrue(payload.get("ok"), msg=payload)
        tools = payload["result"].get("tools", [])
        self.assertIn("run_game_basic_test_flow", tools)
        capabilities = payload["result"].get("tool_capabilities", {})
        flow_capability = capabilities.get("run_game_basic_test_flow", {})
        self.assertTrue(flow_capability.get("implemented"))
        self.assertEqual(flow_capability.get("status"), "implemented")
        self.assertEqual(flow_capability.get("phase"), "runtime_gate_and_virtual_input")

    def test_get_adapter_contract_includes_runtime_requirements(self) -> None:
        code, payload = _run_tool_cli_raw(self.repo_root, "get_adapter_contract", {})
        self.assertEqual(code, 0, msg=f"{payload}")
        self.assertTrue(payload.get("ok"), msg=payload)
        contract = payload.get("result") or {}
        runtime_requirements = contract.get("runtime_requirements") or {}
        self.assertEqual(runtime_requirements.get("input_mode"), "in_engine_virtual_input")
        self.assertFalse(runtime_requirements.get("os_input_interference", True))
        self.assertIn("NOT_IN_PLAY_MODE", contract.get("error_codes", []))

    def test_cli_run_game_basic_test_flow_missing_flow_returns_expected_error(self) -> None:
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {"project_root": str(self.project_root), "flow_id": "missing_flow"},
        )
        self.assertEqual(code, 1, msg=f"expected failure, got: {payload}")
        self.assertFalse(payload.get("ok"))
        err = payload.get("error") or {}
        self.assertEqual(err.get("code"), "INVALID_ARGUMENT")
        self.assertIn("flow file not found", str(err.get("message", "")))

    def test_cli_run_game_basic_test_flow_with_flow_id_succeeds(self) -> None:
        flow_dir = self.project_root / "pointer_gpf" / "generated_flows"
        flow_dir.mkdir(parents=True, exist_ok=True)
        (flow_dir / "smoke_flow.json").write_text(
            json.dumps(
                {
                    "flowId": "smoke_flow",
                    "steps": [{"id": "only", "action": "wait", "until": {"hint": "x"}, "timeoutMs": 100}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        bridge = self.project_root / "pointer_gpf" / "tmp"
        bridge.mkdir(parents=True, exist_ok=True)

        last_seq: list[int | None] = [None]

        def respond() -> None:
            cmd_path = bridge / "command.json"
            rsp_path = bridge / "response.json"
            for _ in range(500):
                if cmd_path.is_file():
                    try:
                        data = json.loads(cmd_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        time.sleep(0.02)
                        continue
                    seq = data.get("seq")
                    if seq is None:
                        time.sleep(0.02)
                        continue
                    if seq == last_seq[0]:
                        time.sleep(0.02)
                        continue
                    last_seq[0] = int(seq)
                    rsp_path.write_text(
                        json.dumps(
                            {"ok": True, "seq": seq, "run_id": data.get("run_id"), "message": "ok"},
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                time.sleep(0.02)

        th = threading.Thread(target=respond, daemon=True)
        th.start()
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {
                "project_root": str(self.project_root),
                "flow_id": "smoke_flow",
                "step_timeout_ms": 8000,
                "shell_report": True,
            },
        )
        self.assertEqual(code, 0, msg=f"expected success, got: {payload}")
        self.assertTrue(payload.get("ok"), msg=payload)
        result = payload.get("result") or {}
        self.assertEqual(result.get("status"), "passed")
        self.assertIn("execution_report", result)
        self.assertIn("exp_runtime", result)
        self.assertTrue((result.get("execution_report") or {}).get("shell_report"))

    def test_cli_run_game_basic_test_flow_with_flow_file_succeeds(self) -> None:
        flow_file = self.work / "seed_flow.json"
        flow_file.write_text(
            json.dumps(
                {
                    "flowId": "seed_flow",
                    "steps": [{"id": "one", "action": "check", "kind": "logic_state"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        bridge = self.project_root / "pointer_gpf" / "tmp"
        bridge.mkdir(parents=True, exist_ok=True)
        last_seq: list[int | None] = [None]

        def respond() -> None:
            cmd_path = bridge / "command.json"
            rsp_path = bridge / "response.json"
            for _ in range(500):
                if cmd_path.is_file():
                    try:
                        data = json.loads(cmd_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        time.sleep(0.02)
                        continue
                    seq = data.get("seq")
                    if seq is None or seq == last_seq[0]:
                        time.sleep(0.02)
                        continue
                    last_seq[0] = int(seq)
                    rsp_path.write_text(
                        json.dumps(
                            {"ok": True, "seq": seq, "run_id": data.get("run_id"), "message": "ok"},
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                time.sleep(0.02)

        th = threading.Thread(target=respond, daemon=True)
        th.start()
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {"project_root": str(self.project_root), "flow_file": str(flow_file), "step_timeout_ms": 8000},
        )
        self.assertEqual(code, 0, msg=f"expected success, got: {payload}")
        self.assertTrue(payload.get("ok"), msg=payload)
        result = payload.get("result") or {}
        self.assertEqual(result.get("status"), "passed")


class FlowExecutionRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.project_root = self.work / "proj"
        self.project_root.mkdir(parents=True, exist_ok=True)
        (self.project_root / "project.godot").write_text('[application]\nconfig/name="tmp"\n', encoding="utf-8")
        self._write_runtime_gate_marker()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_runtime_gate_marker(
        self,
        runtime_mode: str = "play_mode",
        runtime_entry: str = "already_running_play_session",
        runtime_gate_passed: bool = True,
    ) -> None:
        bridge = self.project_root / "pointer_gpf" / "tmp"
        bridge.mkdir(parents=True, exist_ok=True)
        (bridge / "runtime_gate.json").write_text(
            json.dumps(
                {
                    "runtime_mode": runtime_mode,
                    "runtime_entry": runtime_entry,
                    "runtime_gate_passed": runtime_gate_passed,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _start_bridge_responder(self, bridge: Path) -> tuple[threading.Thread, list[int | None]]:
        last_seq: list[int | None] = [None]

        def respond() -> None:
            cmd_path = bridge / "command.json"
            rsp_path = bridge / "response.json"
            for _ in range(2000):
                if cmd_path.is_file():
                    try:
                        data = json.loads(cmd_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        time.sleep(0.02)
                        continue
                    seq = data.get("seq")
                    if seq is None:
                        time.sleep(0.02)
                        continue
                    if seq == last_seq[0]:
                        time.sleep(0.02)
                        continue
                    last_seq[0] = int(seq)
                    rsp_path.write_text(
                        json.dumps(
                            {"ok": True, "seq": seq, "run_id": data.get("run_id"), "message": "simulated"},
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                time.sleep(0.02)

        th = threading.Thread(target=respond, daemon=True)
        th.start()
        return th, last_seq

    def test_run_flow_emits_started_result_verify(self) -> None:
        flow_dir = self.project_root / "pointer_gpf" / "generated_flows"
        flow_dir.mkdir(parents=True, exist_ok=True)
        flow_file = flow_dir / "phase_flow.json"
        flow_file.write_text(
            json.dumps(
                {
                    "flowId": "phase_flow",
                    "steps": [
                        {"id": "step_a", "action": "wait", "until": {"hint": "t"}, "timeoutMs": 100},
                        {"id": "step_b", "action": "check", "kind": "logic_state"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        bridge = self.project_root / "pointer_gpf" / "tmp"
        bridge.mkdir(parents=True, exist_ok=True)
        self._start_bridge_responder(bridge)

        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {"project_root": str(self.project_root), "flow_id": "phase_flow", "step_timeout_ms": 15000},
        )
        self.assertEqual(code, 0, msg=str(payload))
        self.assertTrue(payload.get("ok"), msg=payload)
        report = (payload.get("result") or {}).get("execution_report") or {}
        self.assertEqual(report.get("status"), "passed")
        self.assertEqual(report.get("step_count"), 2)
        self.assertFalse(report.get("shell_report"))
        self.assertEqual(report.get("runtime_mode"), "play_mode")
        self.assertEqual(report.get("runtime_entry"), "already_running_play_session")
        self.assertEqual(report.get("input_mode"), "in_engine_virtual_input")
        self.assertFalse(report.get("os_input_interference"))
        self.assertTrue(report.get("runtime_gate_passed"))
        summary = report.get("step_broadcast_summary") or {}
        self.assertEqual(summary.get("protocol_mode"), "three_phase")
        self.assertTrue(summary.get("fail_fast_on_verify"))
        cov = report.get("phase_coverage") or {}
        self.assertEqual(cov.get("started"), 2)
        self.assertEqual(cov.get("result"), 2)
        self.assertEqual(cov.get("verify"), 2)
        events_path = Path(str(report.get("events_file", "")))
        self.assertTrue(events_path.is_file(), msg=f"missing {events_path}")
        runtime_dir = (self.project_root / "pointer_gpf" / "gpf-exp" / "runtime").resolve()
        self.assertEqual(events_path.parent.resolve(), runtime_dir)
        lines = [ln for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertEqual(len(lines), 6)
        phases = [json.loads(ln).get("phase") for ln in lines]
        self.assertEqual(phases.count("started"), 2)
        self.assertEqual(phases.count("result"), 2)
        self.assertEqual(phases.count("verify"), 2)
        report_path = Path(str(report.get("report_file", "")))
        self.assertTrue(report_path.is_file())
        self.assertEqual(report_path.parent.resolve(), runtime_dir)

    def test_run_flow_require_play_mode_blocks_without_gate_marker(self) -> None:
        flow_dir = self.project_root / "pointer_gpf" / "generated_flows"
        flow_dir.mkdir(parents=True, exist_ok=True)
        (flow_dir / "gate_flow.json").write_text(
            json.dumps(
                {
                    "flowId": "gate_flow",
                    "steps": [{"id": "g1", "action": "wait", "timeoutMs": 50}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        bridge = self.project_root / "pointer_gpf" / "tmp"
        marker = bridge / "runtime_gate.json"
        if marker.exists():
            marker.unlink()

        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {
                "project_root": str(self.project_root),
                "flow_id": "gate_flow",
                "step_timeout_ms": 1000,
                "require_play_mode": True,
            },
        )
        self.assertEqual(code, 1, msg=f"expected gate failure, got: {payload}")
        self.assertFalse(payload.get("ok"))
        err = payload.get("error") or {}
        self.assertEqual(err.get("code"), "RUNTIME_GATE_FAILED")
        details = err.get("details") or {}
        self.assertEqual(details.get("runtime_mode"), "editor_bridge")
        self.assertFalse(details.get("runtime_gate_passed"))

    def test_run_flow_times_out_when_bridge_no_response(self) -> None:
        flow_dir = self.project_root / "pointer_gpf" / "generated_flows"
        flow_dir.mkdir(parents=True, exist_ok=True)
        (flow_dir / "timeout_flow.json").write_text(
            json.dumps(
                {
                    "flowId": "timeout_flow",
                    "steps": [{"id": "lonely", "action": "wait", "timeoutMs": 50}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.project_root / "pointer_gpf" / "tmp").mkdir(parents=True, exist_ok=True)

        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {"project_root": str(self.project_root), "flow_id": "timeout_flow", "step_timeout_ms": 250},
        )
        self.assertEqual(code, 1, msg=f"expected timeout failure, got: {payload}")
        self.assertFalse(payload.get("ok"))
        err = payload.get("error") or {}
        self.assertEqual(err.get("code"), "TIMEOUT")
        details = err.get("details") or {}
        rep = details.get("execution_report") or {}
        self.assertEqual(rep.get("status"), "timeout")
        self.assertEqual(rep.get("phase_coverage", {}).get("started"), 1)
        self.assertEqual(rep.get("phase_coverage", {}).get("result"), 0)

    def test_run_flow_ignores_malformed_seq_and_waits_for_valid_response(self) -> None:
        flow_dir = self.project_root / "pointer_gpf" / "generated_flows"
        flow_dir.mkdir(parents=True, exist_ok=True)
        (flow_dir / "seq_guard_flow.json").write_text(
            json.dumps(
                {
                    "flowId": "seq_guard_flow",
                    "steps": [{"id": "sg1", "action": "wait", "timeoutMs": 100}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        bridge = self.project_root / "pointer_gpf" / "tmp"
        bridge.mkdir(parents=True, exist_ok=True)

        def respond_with_bad_then_good_seq() -> None:
            cmd_path = bridge / "command.json"
            rsp_path = bridge / "response.json"
            seen = False
            for _ in range(1000):
                if cmd_path.is_file():
                    try:
                        data = json.loads(cmd_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        time.sleep(0.01)
                        continue
                    if seen:
                        time.sleep(0.01)
                        continue
                    seen = True
                    # First write malformed seq; runner should ignore this instead of crashing.
                    rsp_path.write_text(
                        json.dumps({"ok": True, "seq": "abc", "run_id": data.get("run_id"), "message": "bad seq"}),
                        encoding="utf-8",
                    )
                    time.sleep(0.05)
                    rsp_path.write_text(
                        json.dumps(
                            {"ok": True, "seq": data.get("seq"), "run_id": data.get("run_id"), "message": "good seq"},
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    return
                time.sleep(0.01)

        th = threading.Thread(target=respond_with_bad_then_good_seq, daemon=True)
        th.start()
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {"project_root": str(self.project_root), "flow_id": "seq_guard_flow", "step_timeout_ms": 5000},
        )
        self.assertEqual(code, 0, msg=str(payload))
        self.assertTrue(payload.get("ok"), msg=payload)
        report = (payload.get("result") or {}).get("execution_report") or {}
        self.assertEqual(report.get("status"), "passed")

    def test_run_flow_marks_failed_when_fail_fast_false_and_step_returns_false(self) -> None:
        flow_dir = self.project_root / "pointer_gpf" / "generated_flows"
        flow_dir.mkdir(parents=True, exist_ok=True)
        (flow_dir / "failed_flow.json").write_text(
            json.dumps(
                {
                    "flowId": "failed_flow",
                    "steps": [{"id": "f1", "action": "check", "kind": "logic_state"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        bridge = self.project_root / "pointer_gpf" / "tmp"
        bridge.mkdir(parents=True, exist_ok=True)
        last_seq: list[int | None] = [None]

        def respond_with_failure() -> None:
            cmd_path = bridge / "command.json"
            rsp_path = bridge / "response.json"
            for _ in range(500):
                if cmd_path.is_file():
                    try:
                        data = json.loads(cmd_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        time.sleep(0.02)
                        continue
                    seq = data.get("seq")
                    if seq is None or seq == last_seq[0]:
                        time.sleep(0.02)
                        continue
                    last_seq[0] = int(seq)
                    rsp_path.write_text(
                        json.dumps(
                            {"ok": False, "seq": seq, "run_id": data.get("run_id"), "message": "assert failed"},
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                time.sleep(0.02)

        th = threading.Thread(target=respond_with_failure, daemon=True)
        th.start()
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {
                "project_root": str(self.project_root),
                "flow_id": "failed_flow",
                "step_timeout_ms": 8000,
                "fail_fast": False,
            },
        )
        self.assertEqual(code, 0, msg=f"expected non-fast-fail response, got: {payload}")
        self.assertTrue(payload.get("ok"), msg=payload)
        report = (payload.get("result") or {}).get("execution_report") or {}
        self.assertEqual(report.get("status"), "failed")
        self.assertEqual(report.get("step_count"), 1)
        cov = report.get("phase_coverage", {})
        self.assertEqual(cov.get("started"), 1)
        self.assertEqual(cov.get("result"), 1)
        self.assertEqual(cov.get("verify"), 1)


class PluginBridgePackagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.project_root = self.work / "proj"
        self.project_root.mkdir(parents=True, exist_ok=True)
        (self.project_root / "project.godot").write_text('[application]\nconfig/name="tmp"\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_install_godot_plugin_includes_runtime_bridge_script(self) -> None:
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "install_godot_plugin",
            {"project_root": str(self.project_root)},
        )
        self.assertEqual(code, 0, msg=f"{payload}")
        self.assertTrue(payload.get("ok"), msg=payload)
        bridge_gd = self.project_root / "addons" / "pointer_gpf" / "runtime_bridge.gd"
        self.assertTrue(bridge_gd.is_file(), msg=f"missing packaged bridge script: {bridge_gd}")

    def test_packaged_runtime_bridge_contains_contract_compatible_semantics(self) -> None:
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "install_godot_plugin",
            {"project_root": str(self.project_root)},
        )
        self.assertEqual(code, 0, msg=f"{payload}")
        self.assertTrue(payload.get("ok"), msg=payload)
        bridge_gd = self.project_root / "addons" / "pointer_gpf" / "runtime_bridge.gd"
        self.assertTrue(bridge_gd.is_file(), msg=f"missing packaged bridge script: {bridge_gd}")
        src = bridge_gd.read_text(encoding="utf-8")
        # Command shape compatibility: supports top-level action and step.action.
        self.assertIn("func _resolve_action(command: Dictionary, step: Dictionary) -> String:", src)
        self.assertIn("var top_level_action := str(command.get(\"action\", \"\")).strip_edges()", src)
        self.assertIn("return str(step.get(\"action\", \"\")).strip_edges()", src)
        # Error compatibility: nested error object and planned codes.
        self.assertIn("\"error\": {\"code\": code, \"message\": message}", src)
        self.assertIn("_write_error_response(\"INVALID_ARGUMENT\", \"command must be a JSON object\", -1, \"\")", src)
        self.assertIn("_write_error_response(\"INVALID_ARGUMENT\", \"seq is required and must be int/float\", -1, run_id)", src)
        self.assertIn("return _error_payload(\"ACTION_NOT_SUPPORTED\", \"unsupported action: %s\" % action, seq, run_id)", src)
        # Action-specific response fields expected by plan examples.
        self.assertIn("\"target\": _extract_target(command, step)", src)
        self.assertIn("\"elapsedMs\": max(0, _coerce_int(step.get(\"timeoutMs\", command.get(\"timeoutMs\", 0))))", src)
        self.assertIn("\"conditionMet\": true", src)
        self.assertIn("\"details\": {\"status\": \"ok\", \"kind\": str(step.get(\"kind\", command.get(\"kind\", \"\")))}", src)
        self.assertIn("\"artifactPath\": str(step.get(\"artifactPath\", command.get(\"artifactPath\", \"user://pointer_gpf_snapshot.png\")))", src)
        # Dedup uses (run_id, seq) so a new run can reuse seq without being skipped.
        self.assertIn("var _last_run_id: String = \"\"", src)
        self.assertIn("run_id == _last_run_id and seq == _last_seq", src)
        # Runtime input contract: in-engine virtual input dispatch and cursor overlay.
        self.assertIn("Input.parse_input_event", src)
        self.assertIn("func _dispatch_click_virtual", src)
        self.assertIn("func _dispatch_move_mouse_virtual", src)
        self.assertIn("func _dispatch_drag_virtual", src)
        self.assertIn("ColorRect", src)
        self.assertIn("Color(1, 0, 0", src)
        self.assertIn("func _show_virtual_cursor", src)
        self.assertIn("func _hide_virtual_cursor", src)
        self.assertIn("\"INPUT_PATH_BLOCKED\"", src)
        # Duplicate delivery: respond then remove command.json to avoid a stuck poll loop.
        self.assertIn("\"duplicate\": true", src)
        self.assertRegex(
            src,
            r"_write_response\([\s\S]*?\"duplicate\":\s*true[\s\S]*?\)[\s\S]*?_delete_command_file\(\)",
        )
        # Ensure command file cleanup is implemented and called after handling.
        self.assertIn("func _delete_command_file() -> void:", src)
        self.assertIn("_write_response(rsp)", src)
        self.assertIn("_delete_command_file()", src)

    def test_packaged_plugin_mounts_bridge_on_scene_tree_root(self) -> None:
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "install_godot_plugin",
            {"project_root": str(self.project_root)},
        )
        self.assertEqual(code, 0, msg=f"{payload}")
        self.assertTrue(payload.get("ok"), msg=payload)
        plugin_gd = self.project_root / "addons" / "pointer_gpf" / "plugin.gd"
        self.assertTrue(plugin_gd.is_file(), msg=f"missing plugin script: {plugin_gd}")
        src = plugin_gd.read_text(encoding="utf-8")
        self.assertIn("get_tree().root.add_child(_runtime_bridge)", src)


def _load_mcp_server_module(repo_root: Path):
    mcp_dir = repo_root / "mcp"
    mcp_str = str(mcp_dir)
    inserted = False
    if mcp_str not in sys.path:
        sys.path.insert(0, mcp_str)
        inserted = True
    try:
        spec = importlib.util.spec_from_file_location(
            "gpf_mcp_server",
            mcp_dir / "server.py",
            submodule_search_locations=[mcp_str],
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("failed to load mcp/server.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if inserted:
            try:
                sys.path.remove(mcp_str)
            except ValueError:
                pass


class McpToolSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]

    def test_design_and_update_basic_flow_schemas_include_strategy_like_generate_flow_seed(self) -> None:
        mod = _load_mcp_server_module(self.repo_root)
        specs = mod._build_tool_specs()
        seed_enum = specs["generate_flow_seed"]["inputSchema"]["properties"]["strategy"]["enum"]
        for name in ("design_game_basic_test_flow", "update_game_basic_design_flow_by_current_state"):
            strat = specs[name]["inputSchema"]["properties"].get("strategy")
            self.assertIsNotNone(strat, msg=f"missing strategy on {name}")
            self.assertEqual(strat.get("type"), "string")
            self.assertEqual(strat.get("enum"), seed_enum)


class DocumentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]

    def test_quickstart_runtime_command_exists(self) -> None:
        quickstart = self.repo_root / "docs" / "quickstart.md"
        self.assertTrue(quickstart.is_file(), msg=f"missing {quickstart}")
        text = quickstart.read_text(encoding="utf-8")
        self.assertIn("run_game_basic_test_flow", text)
        self.assertIn("ValidateExecutionPipeline", text)

    def test_readmes_runtime_command_exists(self) -> None:
        for rel in ("README.md", "README.zh-CN.md"):
            path = self.repo_root / rel
            self.assertTrue(path.is_file(), msg=f"missing {path}")
            text = path.read_text(encoding="utf-8")
            self.assertIn("design_game_basic_test_flow", text)
            self.assertIn("run_game_basic_test_flow", text)
            self.assertIn("ValidateExecutionPipeline", text)

    def test_readme_mentions_auto_fix_game_bug_and_dual_conclusions(self) -> None:
        text = (self.repo_root / "README.zh-CN.md").read_text(encoding="utf-8")
        self.assertIn("auto_fix_game_bug", text)
        self.assertIn("tool_usability", text)
        self.assertIn("gameplay_runnability", text)


if __name__ == "__main__":
    unittest.main()
