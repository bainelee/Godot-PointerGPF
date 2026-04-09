import json
import subprocess
import tempfile
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

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_get_mcp_runtime_info_lists_run_game_basic_test_flow(self) -> None:
        code, payload = _run_tool_cli_raw(self.repo_root, "get_mcp_runtime_info", {})
        self.assertEqual(code, 0, msg=f"{payload}")
        self.assertTrue(payload.get("ok"), msg=payload)
        tools = payload["result"].get("tools", [])
        self.assertIn("run_game_basic_test_flow", tools)
        capabilities = payload["result"].get("tool_capabilities", {})
        flow_capability = capabilities.get("run_game_basic_test_flow", {})
        self.assertFalse(flow_capability.get("implemented"))
        self.assertEqual(flow_capability.get("status"), "not_implemented")

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

    def test_cli_run_game_basic_test_flow_with_flow_id_returns_not_implemented(self) -> None:
        flow_dir = self.project_root / "pointer_gpf" / "generated_flows"
        flow_dir.mkdir(parents=True, exist_ok=True)
        (flow_dir / "smoke_flow.json").write_text("{\"flowId\":\"smoke_flow\"}", encoding="utf-8")
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {"project_root": str(self.project_root), "flow_id": "smoke_flow"},
        )
        self.assertEqual(code, 1, msg=f"expected NOT_IMPLEMENTED failure, got: {payload}")
        self.assertFalse(payload.get("ok"))
        err = payload.get("error") or {}
        self.assertEqual(err.get("code"), "NOT_IMPLEMENTED")

    def test_cli_run_game_basic_test_flow_with_flow_file_returns_not_implemented(self) -> None:
        flow_file = self.work / "seed_flow.json"
        flow_file.write_text("{\"flowId\":\"seed_flow\"}", encoding="utf-8")
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {"project_root": str(self.project_root), "flow_file": str(flow_file)},
        )
        self.assertEqual(code, 1, msg=f"expected NOT_IMPLEMENTED failure, got: {payload}")
        self.assertFalse(payload.get("ok"))
        err = payload.get("error") or {}
        self.assertEqual(err.get("code"), "NOT_IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
