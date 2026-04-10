"""Tests for failure_taxonomy.classify_failure."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import failure_taxonomy as ft  # noqa: E402


class TestFailureTaxonomy(unittest.TestCase):
    def test_runtime_gate_failed_class(self) -> None:
        sig = ft.FailureSignal(app_error_code="RUNTIME_GATE_FAILED", step_status=None, diagnostics_severity=None)
        self.assertEqual(ft.classify_failure(sig), "runtime_gate")

    def test_engine_runtime_stalled_class(self) -> None:
        sig = ft.FailureSignal(app_error_code="ENGINE_RUNTIME_STALLED", step_status=None, diagnostics_severity="error")
        self.assertEqual(ft.classify_failure(sig), "engine_runtime_error")

    def test_step_failed_unknown(self) -> None:
        sig = ft.FailureSignal(app_error_code="STEP_FAILED", step_status="failed", diagnostics_severity=None)
        self.assertEqual(ft.classify_failure(sig), "flow_step_failed")

    def test_step_status_failed_without_app_code(self) -> None:
        sig = ft.FailureSignal(app_error_code=None, step_status="failed", diagnostics_severity=None)
        self.assertEqual(ft.classify_failure(sig), "flow_step_failed")

    def test_flow_generation_blocked(self) -> None:
        sig = ft.FailureSignal("FLOW_GENERATION_BLOCKED", None, None)
        self.assertEqual(ft.classify_failure(sig), "flow_generation_blocked")

    def test_invalid_godot_project(self) -> None:
        sig = ft.FailureSignal("PROJECT_GODOT_NOT_FOUND", None, None)
        self.assertEqual(ft.classify_failure(sig), "invalid_godot_project")


if __name__ == "__main__":
    unittest.main()
