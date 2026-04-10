"""Ensure the minimal example ships the PointerGPF editor addon (teardown parity with template)."""

from __future__ import annotations

import unittest
from pathlib import Path


class TestExamplesMinimalPointerGpfAddonTracked(unittest.TestCase):
    def test_godot_minimal_has_tracked_pointer_gpf_addon(self) -> None:
        root = Path(__file__).resolve().parents[1]
        plugin = root / "examples" / "godot_minimal" / "addons" / "pointer_gpf" / "plugin.gd"
        self.assertTrue(
            plugin.is_file(),
            "examples/godot_minimal must ship addons/pointer_gpf for reproducible teardown",
        )
