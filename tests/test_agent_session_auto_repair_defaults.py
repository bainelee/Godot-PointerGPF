"""Agent session overrides CI-style GPF_AUTO_REPAIR_DEFAULT=0 for implicit auto_repair default."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import server  # noqa: E402


class TestAgentSessionAutoRepairDefaults(unittest.TestCase):
    @mock.patch.dict(os.environ, {"GPF_AUTO_REPAIR_DEFAULT": "0"}, clear=False)
    def test_without_agent_session_auto_repair_off(self) -> None:
        ar, _, _ = server._parse_auto_repair_params({})
        self.assertFalse(ar)

    @mock.patch.dict(os.environ, {"GPF_AUTO_REPAIR_DEFAULT": "0", "GPF_AGENT_SESSION_DEFAULTS": "1"}, clear=False)
    def test_with_env_agent_session_auto_repair_on(self) -> None:
        ar, _, _ = server._parse_auto_repair_params({})
        self.assertTrue(ar)

    @mock.patch.dict(os.environ, {"GPF_AUTO_REPAIR_DEFAULT": "0"}, clear=False)
    def test_with_argument_agent_session_auto_repair_on(self) -> None:
        ar, _, _ = server._parse_auto_repair_params({"agent_session_defaults": True})
        self.assertTrue(ar)

    @mock.patch.dict(os.environ, {"GPF_AUTO_REPAIR_DEFAULT": "0", "GPF_AGENT_SESSION_DEFAULTS": "1"}, clear=False)
    def test_explicit_auto_repair_false_overrides_agent_session(self) -> None:
        ar, _, _ = server._parse_auto_repair_params({"auto_repair": False})
        self.assertFalse(ar)

    def test_tool_specs_include_agent_session_defaults(self) -> None:
        specs = server._build_tool_specs()
        for name in ("run_game_basic_test_flow", "run_game_basic_test_flow_by_current_state"):
            prop = specs[name]["inputSchema"]["properties"].get("agent_session_defaults")
            self.assertIsNotNone(prop, msg=name)
            self.assertEqual(prop.get("type"), "boolean")


if __name__ == "__main__":
    unittest.main()
