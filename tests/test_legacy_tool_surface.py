import importlib.util
import sys
import unittest
from pathlib import Path


def _load_server(repo_root: Path):
    mcp_dir = repo_root / "mcp"
    mcp_str = str(mcp_dir)
    if mcp_str not in sys.path:
        sys.path.insert(0, mcp_str)
    spec = importlib.util.spec_from_file_location("pointer_server", mcp_dir / "server.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class LegacyToolSurfaceTests(unittest.TestCase):
    def test_legacy_tools_are_registered(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        mod = _load_server(repo)
        tool_map = mod._build_tool_map()
        expected = {
            "list_test_scenarios",
            "run_game_test",
            "get_test_artifacts",
            "get_test_report",
            "get_flow_timeline",
            "run_game_flow",
            "get_test_run_status",
            "cancel_test_run",
            "resume_fix_loop",
            "start_game_flow_live",
            "get_live_flow_progress",
            "run_and_stream_flow",
            "start_stepwise_flow",
            "prepare_step",
            "execute_step",
            "verify_step",
            "step_once",
            "run_stepwise_autopilot",
            "start_cursor_chat_plugin",
            "pull_cursor_chat_plugin",
        }
        self.assertTrue(expected.issubset(set(tool_map.keys())))
