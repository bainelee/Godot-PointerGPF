import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


def _run_tool(repo_root: Path, tool: str, args: dict) -> dict:
    payload_args = dict(args)
    if tool in ("run_game_basic_test_flow", "run_game_basic_test_flow_by_current_state"):
        if "auto_repair" not in payload_args:
            payload_args["auto_repair"] = False
    if "project_root" in payload_args and "allow_temp_project" not in payload_args:
        payload_args["allow_temp_project"] = True
    cmd = [
        sys.executable,
        str(repo_root / "mcp" / "server.py"),
        "--tool",
        tool,
        "--args",
        json.dumps(payload_args, ensure_ascii=False),
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError(f"tool {tool} failed: {proc.stdout}\n{proc.stderr}")
    payload = json.loads(proc.stdout)
    if not payload.get("ok"):
        raise AssertionError(f"tool {tool} returned error: {json.dumps(payload, ensure_ascii=False)}")
    return payload["result"]


def _start_bridge_responder(project_root: Path) -> threading.Thread:
    bridge = project_root / "pointer_gpf" / "tmp"
    bridge.mkdir(parents=True, exist_ok=True)
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
                        {"ok": True, "seq": seq, "run_id": data.get("run_id"), "message": "ok"},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            time.sleep(0.02)

    th = threading.Thread(target=respond, daemon=True)
    th.start()
    return th


class NaturalLanguageBasicFlowCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp.name) / "proj"
        self.project_root.mkdir(parents=True, exist_ok=True)
        (self.project_root / "project.godot").write_text('[application]\nconfig/name="tmp"\n', encoding="utf-8")

        scripts_dir = self.project_root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "player.gd").write_text(
            "\n".join(
                [
                    "extends Node",
                    "",
                    "func _on_start_pressed():",
                    "    pass",
                    "",
                    "func save_game():",
                    "    pass",
                    "",
                    "func load_game():",
                    "    pass",
                    "",
                    "func move_player():",
                    "    pass",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        scenes_dir = self.project_root / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        (scenes_dir / "main.tscn").write_text(
            "\n".join(
                [
                    "[gd_scene format=3]",
                    '[node name="MainUI" type="Control"]',
                ]
            ),
            encoding="utf-8",
        )
        bridge = self.project_root / "pointer_gpf" / "tmp"
        bridge.mkdir(parents=True, exist_ok=True)
        (bridge / "runtime_gate.json").write_text(
            json.dumps(
                {
                    "runtime_mode": "play_mode",
                    "runtime_entry": "already_running_play_session",
                    "runtime_gate_passed": True,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_design_game_basic_test_flow_uses_evidence_driven_steps(self) -> None:
        result = _run_tool(
            self.repo_root,
            "design_game_basic_test_flow",
            {
                "project_root": str(self.project_root),
                "flow_id": "nl_basic_test_flow",
                "max_feature_checks": 2,
            },
        )
        self.assertEqual(result["status"], "generated")
        flow_file = Path(result["flow_file"])
        self.assertTrue(flow_file.exists())
        payload = json.loads(flow_file.read_text(encoding="utf-8"))
        step_ids = [step["id"] for step in payload["steps"]]
        self.assertIn("launch_game", step_ids)
        self.assertIn("enter_game", step_ids)
        self.assertIn("feature_assert_1", step_ids)
        self.assertIn("snapshot_end", step_ids)
        # save/load 不再由方法名关键词直接触发，必须具备 UI 入口证据。
        self.assertNotIn("save_game_smoke", step_ids)
        self.assertNotIn("load_game_smoke", step_ids)
        generation_evidence = payload.get("generation_evidence") or {}
        counts = generation_evidence.get("candidate_counts") or {}
        self.assertGreaterEqual(int(counts.get("action_filtered", 0)), 1)

    def test_design_game_basic_test_flow_returns_blocked_without_executable_evidence(self) -> None:
        # 删除关键可交互方法，构造“无可执行动作证据”的项目。
        scripts_dir = self.project_root / "scripts"
        (scripts_dir / "player.gd").write_text(
            "\n".join(
                [
                    "extends Node",
                    "",
                    "func save_game():",
                    "    pass",
                    "",
                    "func load_game():",
                    "    pass",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        scenes_dir = self.project_root / "scenes"
        (scenes_dir / "main.tscn").write_text(
            "\n".join(
                [
                    "[gd_scene format=3]",
                    '[node name="Main" type="Node"]',
                ]
            ),
            encoding="utf-8",
        )
        result = _run_tool(
            self.repo_root,
            "design_game_basic_test_flow",
            {
                "project_root": str(self.project_root),
                "flow_id": "nl_blocked_flow",
                "max_feature_checks": 2,
            },
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(str(result.get("flow_file", "")), "")
        reasons = result.get("reasons") or []
        self.assertIn("no_executable_action_candidates", reasons)

    def test_update_game_basic_design_flow_by_current_state_refreshes_first(self) -> None:
        result = _run_tool(
            self.repo_root,
            "update_game_basic_design_flow_by_current_state",
            {
                "project_root": str(self.project_root),
                "flow_id": "nl_basic_test_flow_update",
            },
        )
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["context_refresh"]["status"], "refreshed")
        self.assertEqual(result["flow_result"]["status"], "generated")
        self.assertTrue(Path(result["flow_result"]["flow_file"]).exists())

    def test_update_then_run_basic_flow(self) -> None:
        _start_bridge_responder(self.project_root)
        updated = _run_tool(
            self.repo_root,
            "update_game_basic_design_flow_by_current_state",
            {"project_root": str(self.project_root), "flow_id": "nl_exec_flow"},
        )
        self.assertEqual(updated["status"], "updated")
        run = _run_tool(
            self.repo_root,
            "run_game_basic_test_flow",
            {"project_root": str(self.project_root), "flow_id": "nl_exec_flow", "step_timeout_ms": 2000},
        )
        self.assertIn(run["status"], ("passed", "failed"))
        self.assertIn("execution_report", run)

    def test_run_game_basic_test_flow_by_current_state_returns_execution_result(self) -> None:
        _start_bridge_responder(self.project_root)
        result = _run_tool(
            self.repo_root,
            "run_game_basic_test_flow_by_current_state",
            {"project_root": str(self.project_root), "flow_id": "nl_exec_orchestration_flow", "step_timeout_ms": 2000},
        )
        self.assertIn("context_refresh", result)
        self.assertIn("flow_result", result)
        self.assertIn("execution_result", result)
        self.assertEqual(result["context_refresh"]["status"], "refreshed")

        flow_result = result["flow_result"]
        flow_file = str(flow_result.get("flow_file", "")).strip()
        self.assertTrue(flow_file)
        self.assertTrue(Path(flow_file).exists())

        execution_result = result["execution_result"]
        execution_status = execution_result.get("status")
        self.assertIn(execution_status, ("passed", "failed", "timeout"))
        status_mapping = {"passed": "passed", "failed": "failed", "timeout": "failed"}
        self.assertEqual(result.get("status"), status_mapping[execution_status])

        self.assertIn("execution_report", execution_result)
        execution_report = execution_result["execution_report"]
        self.assertEqual(execution_report.get("status"), execution_status)

    def test_nl_aliases_map_to_basic_flow_tools(self) -> None:
        aliases = [
            "设计一个基础测试流程",
            "生成基础测试流程",
            "跑一遍基础测试流程",
            "要求跑基础测试流程",
        ]
        for phrase in aliases:
            result = _run_tool(
                self.repo_root,
                "route_nl_intent",
                {"text": phrase},
            )
            self.assertIn(
                result.get("target_tool"),
                {
                    "design_game_basic_test_flow",
                    "run_game_basic_test_flow_by_current_state",
                },
            )

    def test_run_basic_flow_returns_dual_conclusions_and_readable_broadcast(self) -> None:
        _start_bridge_responder(self.project_root)
        result = _run_tool(
            self.repo_root,
            "run_game_basic_test_flow_by_current_state",
            {"project_root": str(self.project_root), "flow_id": "dual_conclusion_flow", "shell_report": True},
        )
        execution = result["execution_result"]
        self.assertIn("tool_usability", execution)
        self.assertIn("gameplay_runnability", execution)
        self.assertIn("step_broadcast_summary", execution)
        summary = execution.get("step_broadcast_summary", {})
        self.assertIsInstance(summary, dict)
        gameplay = execution.get("gameplay_runnability") or {}
        self.assertTrue(gameplay.get("passed"))
        evidence = gameplay.get("evidence") or {}
        self.assertEqual(evidence.get("runtime_mode"), "play_mode")
        self.assertTrue(evidence.get("runtime_gate_passed"))
        self.assertEqual(evidence.get("input_mode"), "in_engine_virtual_input")
        self.assertFalse(evidence.get("os_input_interference", True))


if __name__ == "__main__":
    unittest.main()
