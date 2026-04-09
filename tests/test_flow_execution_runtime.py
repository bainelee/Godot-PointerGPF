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

    def test_cli_run_game_basic_test_flow_missing_flow_returns_expected_error(self) -> None:
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "run_game_basic_test_flow",
            {"project_root": str(self.project_root)},
        )
        self.assertEqual(code, 1, msg=f"expected failure, got: {payload}")
        self.assertFalse(payload.get("ok"))
        err = payload.get("error") or {}
        self.assertIn(err.get("code"), ("INVALID_ARGUMENT", "NOT_IMPLEMENTED"))


if __name__ == "__main__":
    unittest.main()
