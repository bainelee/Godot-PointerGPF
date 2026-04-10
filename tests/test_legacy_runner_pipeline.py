"""Legacy gameplayflow runner：run_game_flow 返回结构最小校验。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LegacyRunnerPipelineTests(unittest.TestCase):
    def test_run_game_flow_generates_report_and_timeline(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir(parents=True, exist_ok=True)
            (project / "project.godot").write_text(
                '[application]\nconfig/name="tmp"\n',
                encoding="utf-8",
            )
            flow_file = project / "pointer_gpf" / "generated_flows" / "legacy_test.json"
            flow_file.parent.mkdir(parents=True, exist_ok=True)
            flow_file.write_text(
                json.dumps(
                    {
                        "flowId": "legacy_test",
                        "steps": [{"id": "s1", "action": "wait", "timeoutMs": 100}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tool_args = {
                "project_root": str(project.resolve()),
                "flow_file": str(flow_file.resolve()),
                "dry_run": True,
                "allow_non_broadcast": True,
            }
            env = os.environ.copy()
            env["MCP_ALLOW_NON_BROADCAST"] = "1"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(repo / "mcp" / "server.py"),
                    "--tool",
                    "run_game_flow",
                    "--args",
                    json.dumps(tool_args, ensure_ascii=False),
                ],
                cwd=str(repo),
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, msg=f"{proc.stdout}\n{proc.stderr}")
            payload = json.loads(proc.stdout)
            self.assertTrue(payload.get("ok"), msg=payload)
            result = payload["result"]
            self.assertIn("run_id", result)
            self.assertIn("report_file", result)
            self.assertIn("flow_report_file", result)
            self.assertTrue(str(result["report_file"]).strip())
            self.assertTrue(str(result["flow_report_file"]).strip())


if __name__ == "__main__":
    unittest.main()
