import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


def _run_tool_cli(repo_root: Path, tool: str, args: dict) -> tuple[int, dict]:
    cmd = [
        sys.executable,
        str(repo_root / "mcp" / "server.py"),
        "--tool",
        tool,
        "--args",
        json.dumps(args, ensure_ascii=False),
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


class AutoFixGameBugCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp.name) / "proj"
        self.project_root.mkdir(parents=True, exist_ok=True)
        (self.project_root / "project.godot").write_text('[application]\nconfig/name="tmp"\n', encoding="utf-8")

        scripts_dir = self.project_root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "player.gd").write_text("extends Node\nfunc _on_start_pressed() -> void:\n    pass\n", encoding="utf-8")

        scenes_dir = self.project_root / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        (scenes_dir / "main.tscn").write_text('[gd_scene format=3]\n[node name="Root" type="Node"]\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _start_bridge_fail(self) -> None:
        bridge = self.project_root / "pointer_gpf" / "tmp"
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
                            {
                                "ok": False,
                                "seq": seq,
                                "run_id": data.get("run_id"),
                                "message": "step failed",
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                time.sleep(0.02)

        threading.Thread(target=respond, daemon=True).start()

    def test_auto_fix_bug_runs_full_loop_until_success_or_timeout(self) -> None:
        self._start_bridge_fail()
        code, payload = _run_tool_cli(
            self.repo_root,
            "auto_fix_game_bug",
            {
                "project_root": str(self.project_root),
                "allow_temp_project": True,
                "issue": "这个按钮无法点击",
                "max_cycles": 2,
                "timeout_seconds": 60,
                "step_timeout_ms": 3000,
            },
        )
        self.assertEqual(code, 0, msg=payload)
        self.assertTrue(payload.get("ok"), msg=payload)
        result = payload.get("result") or {}
        self.assertIn(result.get("final_status"), {"fixed", "timeout", "not_fixed"})
        self.assertGreaterEqual(int(result.get("cycles_completed", 0)), 1)
        self.assertIsInstance(result.get("loop_evidence"), list)
        self.assertTrue(result["loop_evidence"])
        first = result["loop_evidence"][0]
        self.assertIn("verification", first)
        self.assertIn("diagnosis", first)
        self.assertIn("patch", first)
        self.assertIn("retest", first)


if __name__ == "__main__":
    unittest.main()
