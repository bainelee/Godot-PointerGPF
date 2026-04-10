"""Tests for additional bug-fix strategies (scene / signal hint)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

from bug_fix_strategies import (  # noqa: E402
    SceneButtonDisabledFalseStrategy,
    SceneMouseFilterPassStrategy,
    SignalDisconnectedHintStrategy,
    run_apply_patch,
    run_diagnosis,
    select_strategy,
)


class BugFixStrategiesExtraTests(unittest.TestCase):
    def test_select_signal_strategy(self) -> None:
        s = select_strategy("开始按钮的信号未连接到脚本")
        self.assertIsNotNone(s)
        assert s is not None
        self.assertEqual(s.strategy_id, "signal_disconnected_hint")

    def test_signal_hint_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            root.mkdir(parents=True, exist_ok=True)
            (root / "project.godot").write_text('[application]\nconfig/name="t"\n', encoding="utf-8")
            issue = "pressed 信号没连线"
            strat = SignalDisconnectedHintStrategy()
            diag = strat.diagnose(issue, {"status": "failed"})
            res = strat.apply_patch(root, diag)
            self.assertTrue(res.get("applied"))
            paths = res.get("changed_files") or []
            self.assertEqual(len(paths), 1)
            data = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
            self.assertEqual(data.get("strategy_id"), "signal_disconnected_hint")

    def test_disabled_false_patches_tscn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            scenes = root / "scenes"
            scenes.mkdir(parents=True, exist_ok=True)
            tscn = scenes / "ui.tscn"
            tscn.write_text(
                "\n".join(
                    [
                        "[gd_scene format=3]",
                        '[node name="Start" type="Button" parent="."]',
                        "disabled = true",
                    ]
                ),
                encoding="utf-8",
            )
            strat = SceneButtonDisabledFalseStrategy()
            issue = "开始按钮被禁用"
            self.assertTrue(strat.matches(issue))
            diag = strat.diagnose(issue, {})
            res = strat.apply_patch(root, diag)
            self.assertTrue(res.get("applied"))
            self.assertIn("disabled = false", tscn.read_text(encoding="utf-8"))

    def test_mouse_filter_pass_patches_tscn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            scenes = root / "scenes"
            scenes.mkdir(parents=True, exist_ok=True)
            tscn = scenes / "layer.tscn"
            tscn.write_text(
                "\n".join(
                    [
                        "[gd_scene format=3]",
                        '[node name="Blocker" type="Control" parent="."]',
                        "mouse_filter = 0",
                    ]
                ),
                encoding="utf-8",
            )
            strat = SceneMouseFilterPassStrategy()
            issue = "父层 mouse_filter 设置导致子按钮点不到"
            self.assertTrue(strat.matches(issue))
            diag = strat.diagnose(issue, {})
            res = strat.apply_patch(root, diag)
            self.assertTrue(res.get("applied"))
            self.assertIn("mouse_filter = 2", tscn.read_text(encoding="utf-8"))

    def test_run_apply_patch_uses_diagnosis_strategy_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            root.mkdir(parents=True, exist_ok=True)
            (root / "project.godot").write_text('[application]\nconfig/name="t"\n', encoding="utf-8")
            issue = "槽函数信号 not connected 到按钮"
            verification: dict = {"status": "failed"}
            diagnosis = run_diagnosis(issue, verification)
            patch = run_apply_patch(root, issue, diagnosis)
            self.assertTrue(patch.get("applied"))


if __name__ == "__main__":
    unittest.main()
