#!/usr/bin/env python3
"""Unified MCP adapter for game test runner."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

CORE_DIR = Path(__file__).resolve().parents[1] / "core"
MCP_DIR = Path(__file__).resolve().parent
VERSION_MANIFEST_PATH = MCP_DIR / "version_manifest.json"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from server_errors import AppError  # noqa: E402
from server_handlers_core import CoreHandlersMixin  # noqa: E402
from server_handlers_fixloop import FixLoopHandlersMixin  # noqa: E402
from server_handlers_live import LiveHandlersMixin  # noqa: E402
from server_handlers_stepwise_support import StepwiseSupportMixin  # noqa: E402
from server_handlers_stepwise_ops import StepwiseOpsHandlersMixin  # noqa: E402
from server_handlers_stepwise_autopilot import StepwiseAutopilotHandlersMixin  # noqa: E402
from server_handlers_cursor_chat_plugin import CursorChatPluginHandlersMixin  # noqa: E402


class GameTestMcpServer(
    CoreHandlersMixin,
    FixLoopHandlersMixin,
    LiveHandlersMixin,
    StepwiseSupportMixin,
    StepwiseOpsHandlersMixin,
    StepwiseAutopilotHandlersMixin,
    CursorChatPluginHandlersMixin,
):
    """Single MCP server surface for core/fixloop/live/stepwise/chat tools."""

    TOOL_TO_METHOD: dict[str, str] = {
        "get_mcp_runtime_info": "get_mcp_runtime_info",
        "list_test_scenarios": "list_test_scenarios",
        "run_game_test": "run_game_test",
        "check_test_runner_environment": "check_test_runner_environment",
        "get_test_artifacts": "get_test_artifacts",
        "get_test_report": "get_test_report",
        "get_flow_timeline": "get_flow_timeline",
        "run_game_flow": "run_game_flow",
        "get_test_run_status": "get_test_run_status",
        "cancel_test_run": "cancel_test_run",
        "resume_fix_loop": "resume_fix_loop",
        "start_game_flow_live": "start_game_flow_live",
        "get_live_flow_progress": "get_live_flow_progress",
        "run_and_stream_flow": "run_and_stream_flow",
        "start_stepwise_flow": "start_stepwise_flow",
        "prepare_step": "prepare_step",
        "execute_step": "execute_step",
        "verify_step": "verify_step",
        "step_once": "step_once",
        "run_stepwise_autopilot": "run_stepwise_autopilot",
        "start_cursor_chat_plugin": "start_cursor_chat_plugin",
        "pull_cursor_chat_plugin": "pull_cursor_chat_plugin",
    }
    SNAPSHOT_REQUIRED_TOOLS: set[str] = {
        "check_test_runner_environment",
        "run_game_flow",
        "get_test_artifacts",
        "get_test_report",
        "get_mcp_runtime_info",
        "start_cursor_chat_plugin",
        "pull_cursor_chat_plugin",
    }

    RELAY_ALLOWED_TOOLS: set[str] = {
        "list_test_scenarios",
        "check_test_runner_environment",
        "get_test_artifacts",
        "get_test_report",
        "get_flow_timeline",
        "get_test_run_status",
        "cancel_test_run",
        "pull_cursor_chat_plugin",
        "start_cursor_chat_plugin",
    }
    RELAY_SESSION_ALLOWED_TOOLS: set[str] = {
        "pull_cursor_chat_plugin",
        "get_test_artifacts",
        "get_test_report",
        "get_flow_timeline",
        "get_test_run_status",
        "cancel_test_run",
    }
    BROADCAST_REQUIRED_TOOLS: set[str] = {
        "run_game_test",
        "run_game_flow",
        "start_game_flow_live",
        "run_and_stream_flow",
        "start_stepwise_flow",
        "prepare_step",
        "execute_step",
        "verify_step",
        "step_once",
        "run_stepwise_autopilot",
    }
    MIXIN_OVERRIDES_ALLOWED: set[str] = {"__init__"}

    def __init__(self, default_project_root: Path) -> None:
        self._assert_no_mixin_method_collisions()
        self.default_project_root = default_project_root.resolve()
        self.core_dir = CORE_DIR

    @classmethod
    def _assert_no_mixin_method_collisions(cls) -> None:
        owners: dict[str, str] = {}
        collisions: dict[str, list[str]] = {}
        for mixin in (
            CoreHandlersMixin,
            FixLoopHandlersMixin,
            LiveHandlersMixin,
            StepwiseSupportMixin,
            StepwiseOpsHandlersMixin,
            StepwiseAutopilotHandlersMixin,
            CursorChatPluginHandlersMixin,
        ):
            mixin_name = mixin.__name__
            for name, value in mixin.__dict__.items():
                if name in cls.MIXIN_OVERRIDES_ALLOWED:
                    continue
                if not callable(value):
                    continue
                if name in owners:
                    collisions.setdefault(name, [owners[name]]).append(mixin_name)
                else:
                    owners[name] = mixin_name
        if collisions:
            details = "; ".join(f"{name}: {', '.join(owning)}" for name, owning in sorted(collisions.items()))
            raise RuntimeError(f"mixin method name collision detected: {details}")

    def _enforce_chat_relay_gate(self, tool_name: str, arguments: dict[str, Any]) -> None:
        relay_required = bool(arguments.get("chat_relay_required", False))
        if not relay_required:
            return
        if tool_name in self.RELAY_ALLOWED_TOOLS:
            return
        raise AppError(
            "CHAT_RELAY_REQUIRED",
            "chat_relay_required=true only allows cursor chat relay tools and query/cancel tools",
            {
                "tool": tool_name,
                "allowed_tools": sorted(self.RELAY_ALLOWED_TOOLS),
            },
        )

    @staticmethod
    def _extract_run_id(arguments: dict[str, Any]) -> str:
        return str(arguments.get("run_id", "")).strip()

    def _load_plugin_state_by_run_id(self, run_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not run_id:
            return {}
        try:
            run_root = self._resolve_run_root(run_id, arguments)
        except AppError:
            return {}
        state_path = run_root / "cursor_chat_plugin_state.json"
        if not state_path.exists():
            return {}
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _enforce_chat_relay_session_gate(self, tool_name: str, arguments: dict[str, Any]) -> None:
        run_id = self._extract_run_id(arguments)
        if not run_id:
            return
        plugin_state = self._load_plugin_state_by_run_id(run_id, arguments)
        if not plugin_state:
            return
        relay_locked = bool(plugin_state.get("relay_required", False)) or (
            str(plugin_state.get("relay_policy", "")).strip() == "session_locked"
        )
        if not relay_locked:
            return
        if tool_name in self.RELAY_SESSION_ALLOWED_TOOLS:
            return
        raise AppError(
            "CHAT_RELAY_SESSION_REQUIRED",
            "this run_id is locked to chat relay session policy",
            {
                "run_id": run_id,
                "tool": tool_name,
                "allowed_tools": sorted(self.RELAY_SESSION_ALLOWED_TOOLS),
            },
        )

    def _enforce_broadcast_entry_gate(self, tool_name: str, arguments: dict[str, Any]) -> None:
        if tool_name not in self.BROADCAST_REQUIRED_TOOLS:
            return
        if bool(arguments.get("allow_non_broadcast", False)):
            if str(os.environ.get("MCP_ALLOW_NON_BROADCAST", "")).strip() != "1":
                raise AppError(
                    "BROADCAST_BYPASS_DENIED",
                    "allow_non_broadcast requires MCP_ALLOW_NON_BROADCAST=1 (first-party scripts must use chat/stepwise instead)",
                    {
                        "tool": tool_name,
                        "preferred_tool": "start_cursor_chat_plugin",
                        "env_hint": "MCP_ALLOW_NON_BROADCAST=1",
                    },
                )
            return
        raise AppError(
            "BROADCAST_ENTRY_REQUIRED",
            "this execution tool is disabled by default; use start_cursor_chat_plugin for guaranteed broadcast",
            {
                "tool": tool_name,
                "preferred_tool": "start_cursor_chat_plugin",
                "bypass_argument": "allow_non_broadcast=true",
            },
        )

    def get_mcp_runtime_info(self, _arguments: dict[str, Any]) -> dict[str, Any]:
        manifest_payload: dict[str, Any] = {}
        if VERSION_MANIFEST_PATH.exists():
            try:
                parsed = json.loads(VERSION_MANIFEST_PATH.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    manifest_payload = parsed
            except json.JSONDecodeError:
                manifest_payload = {}
        current_version = str(manifest_payload.get("current_version", "")).strip()
        return {
            "server_name": "game-test-runner-mcp",
            "server_version": current_version or "dev",
            "tool_count": len(self.TOOL_TO_METHOD),
            "tools": sorted(self.TOOL_TO_METHOD.keys()),
            "relay_allowed_tools": sorted(self.RELAY_ALLOWED_TOOLS),
            "broadcast_required_tools": sorted(self.BROADCAST_REQUIRED_TOOLS),
            "broadcast_policy_default": "chat_plugin_only",
            "broadcast_bypass_requires_env": "MCP_ALLOW_NON_BROADCAST=1",
            "version_manifest_path": str(VERSION_MANIFEST_PATH),
            "version_manifest_loaded": bool(manifest_payload),
            "update_policy": manifest_payload.get("update_policy", {}),
            "channels": manifest_payload.get("channels", {}),
        }

    def invoke(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        method_name = self.TOOL_TO_METHOD.get(tool_name, "")
        if not method_name:
            raise AppError("UNSUPPORTED_TOOL", f"unsupported tool: {tool_name}")
        self._enforce_chat_relay_gate(tool_name, arguments)
        self._enforce_chat_relay_session_gate(tool_name, arguments)
        self._enforce_broadcast_entry_gate(tool_name, arguments)
        method = getattr(self, method_name, None)
        if not callable(method):
            raise AppError("INTERNAL_ERROR", f"tool handler not implemented: {tool_name}")
        return method(arguments)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified MCP adapter for game test runner.")
    parser.add_argument("--tool", required=True, help="Tool name")
    parser.add_argument("--args", default="{}", help="JSON string arguments")
    parser.add_argument("--project-root", default=None, help="Default project root")
    parser.add_argument("--system", default=None, help="Shortcut for run_game_test.system")
    parser.add_argument("--scenario", default=None, help="Shortcut for run_game_test.scenario")
    parser.add_argument("--dry-run", action="store_true", help="Shortcut for run_game_test.dry_run")
    parser.add_argument("--run-id", default=None, help="Shortcut for report/artifact query run_id")
    parser.add_argument("--format", default=None, help="Shortcut for get_test_report format")
    parser.add_argument("--flow-file", default=None, help="Shortcut for run_game_flow flow_file")
    parser.add_argument(
        "--allow-non-broadcast",
        action="store_true",
        help="Shortcut to set allow_non_broadcast=true for broadcast-gated tools",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    default_root = (
        Path(args.project_root).resolve()
        if args.project_root
        else Path(__file__).resolve().parents[3]
    )
    server = GameTestMcpServer(default_project_root=default_root)
    try:
        tool_args = json.loads(args.args)
        if not isinstance(tool_args, dict):
            raise AppError("INVALID_ARGUMENT", "args must be a JSON object")
        if args.tool == "run_game_test":
            if args.system is not None:
                tool_args["system"] = args.system
            if args.scenario is not None:
                tool_args["scenario"] = args.scenario
            if args.dry_run:
                tool_args["dry_run"] = True
        if args.tool in {
            "get_test_artifacts",
            "get_test_report",
            "get_test_run_status",
            "cancel_test_run",
            "resume_fix_loop",
            "get_live_flow_progress",
            "pull_cursor_chat_plugin",
            "prepare_step",
            "execute_step",
            "verify_step",
            "step_once",
            "run_stepwise_autopilot",
            "get_flow_timeline",
        }:
            if args.run_id is not None:
                tool_args["run_id"] = args.run_id
        if args.tool in {
            "run_game_flow",
            "start_game_flow_live",
            "run_and_stream_flow",
            "start_stepwise_flow",
            "start_cursor_chat_plugin",
            "run_stepwise_autopilot",
        } and args.flow_file is not None:
            tool_args["flow_file"] = args.flow_file
            if args.dry_run:
                tool_args["dry_run"] = True
        if args.allow_non_broadcast:
            tool_args["allow_non_broadcast"] = True
        if args.tool == "get_test_report" and args.format is not None:
            tool_args["format"] = args.format
        result = server.invoke(args.tool, tool_args)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except AppError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        print(
            json.dumps(
                {"ok": False, "error": {"code": "INTERNAL_ERROR", "message": str(exc)}},
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
