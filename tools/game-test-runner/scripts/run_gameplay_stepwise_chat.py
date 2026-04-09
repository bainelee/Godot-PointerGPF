#!/usr/bin/env python3
"""Legacy 入口：分步执行 + Cursor Chat 插件事件流（调用根目录 mcp/server.py）。

优先路径：`start_cursor_chat_plugin` → `pull_cursor_chat_plugin`（三阶段协议）。
非播报场景需设置环境变量 `MCP_ALLOW_NON_BROADCAST=1` 并在参数中传 `allow_non_broadcast: true`。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _call(tool: str, args: dict) -> subprocess.CompletedProcess[str]:
    repo = _repo_root()
    return subprocess.run(
        [
            sys.executable,
            str(repo / "mcp" / "server.py"),
            "--tool",
            tool,
            "--args",
            json.dumps(args, ensure_ascii=False),
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Stepwise / chat relay helper for legacy gameplayflow MCP tools.")
    parser.add_argument("--project-root", required=True, help="Godot project root")
    parser.add_argument("--flow-file", required=True, help="Flow JSON path (absolute or relative to project)")
    parser.add_argument(
        "--tool",
        default="start_stepwise_flow",
        choices=("start_stepwise_flow", "start_cursor_chat_plugin"),
        help="Which entry tool to invoke",
    )
    args = parser.parse_args()
    payload: dict = {"project_root": str(Path(args.project_root).resolve()), "flow_file": args.flow_file}
    proc = _call(args.tool, payload)
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
