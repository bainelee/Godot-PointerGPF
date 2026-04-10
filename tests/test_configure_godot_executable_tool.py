"""Tests for configure_godot_executable MCP tool."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _run_tool_cli_raw(repo_root: Path, tool: str, args: dict) -> tuple[int, dict]:
    import subprocess

    payload_args = dict(args)
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
    return proc.returncode, json.loads(proc.stdout)


class ConfigureGodotExecutableToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = REPO
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.project_root = self.work / "proj"
        self.project_root.mkdir(parents=True, exist_ok=True)
        (self.project_root / "project.godot").write_text('[application]\nconfig/name="tmp"\n', encoding="utf-8")
        self.fake_exe = self.work / "FakeGodot.exe"
        self.fake_exe.write_bytes(b"")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_configure_godot_executable_writes_json(self) -> None:
        code, payload = _run_tool_cli_raw(
            self.repo_root,
            "configure_godot_executable",
            {
                "project_root": str(self.project_root),
                "godot_executable": str(self.fake_exe),
            },
        )
        self.assertEqual(code, 0, msg=str(payload))
        self.assertTrue(payload.get("ok"), msg=payload)
        result = payload.get("result") or {}
        self.assertEqual(result.get("status"), "written")
        cfg = self.project_root / "tools" / "game-test-runner" / "config" / "godot_executable.json"
        self.assertTrue(cfg.is_file(), msg=f"missing {cfg}")
        data = json.loads(cfg.read_text(encoding="utf-8"))
        self.assertEqual(data.get("godot_executable"), str(self.fake_exe.resolve()))


if __name__ == "__main__":
    unittest.main()
