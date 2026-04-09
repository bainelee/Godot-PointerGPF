#!/usr/bin/env python3
"""Validate MCP tool surface invariants for CI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CORE_DIR = Path(__file__).resolve().parent
MCP_DIR = CORE_DIR.parent / "mcp"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from server import AppError, GameTestMcpServer  # noqa: E402


def _record(name: str, ok: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "ok": ok, "details": details}


def run_snapshot(project_root: Path) -> tuple[dict[str, Any], int]:
    server = GameTestMcpServer(default_project_root=project_root)
    payload = server.invoke("get_mcp_runtime_info", {})
    required_tools = set(GameTestMcpServer.SNAPSHOT_REQUIRED_TOOLS)
    expected_relay_allowed = set(GameTestMcpServer.RELAY_ALLOWED_TOOLS)

    tools = payload.get("tools", [])
    relay_allowed = payload.get("relay_allowed_tools", [])
    tool_count = int(payload.get("tool_count", 0))
    if not isinstance(tools, list):
        tools = []
    if not isinstance(relay_allowed, list):
        relay_allowed = []

    tools_set = set(str(x) for x in tools)
    relay_set = set(str(x) for x in relay_allowed)

    cases: list[dict[str, Any]] = []
    cases.append(
        _record(
            "tool_count_matches_tools_list",
            tool_count == len(tools),
            {"tool_count": tool_count, "tools_len": len(tools)},
        )
    )
    missing_required = sorted(required_tools.difference(tools_set))
    cases.append(
        _record(
            "required_tools_present",
            len(missing_required) == 0,
            {"missing_required_tools": missing_required},
        )
    )
    relay_subset_ok = relay_set.issubset(tools_set)
    cases.append(
        _record(
            "relay_subset_of_tools",
            relay_subset_ok,
            {"unexpected_relay_tools": sorted(relay_set.difference(tools_set))},
        )
    )
    relay_exact_ok = relay_set == expected_relay_allowed
    cases.append(
        _record(
            "relay_allowed_contract",
            relay_exact_ok,
            {
                "expected": sorted(expected_relay_allowed),
                "actual": sorted(relay_set),
            },
        )
    )
    runtime_name_ok = str(payload.get("server_name", "")) == "game-test-runner-mcp"
    cases.append(
        _record(
            "server_name_contract",
            runtime_name_ok,
            {"server_name": payload.get("server_name", "")},
        )
    )

    status = "passed" if all(c["ok"] for c in cases) else "failed"
    out = {
        "status": status,
        "server_version": payload.get("server_version", ""),
        "tool_count": tool_count,
        "cases": cases,
    }
    return out, (0 if status == "passed" else 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate MCP tool surface snapshot.")
    parser.add_argument("--project-root", required=True, help="Project root path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    project_root = Path(args.project_root).resolve()
    try:
        payload, code = run_snapshot(project_root=project_root)
        print(json.dumps(payload, ensure_ascii=False))
        return code
    except AppError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
