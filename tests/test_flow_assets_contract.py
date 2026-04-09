from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_flow_runner(repo_root: Path):
    core = repo_root / "tools" / "game-test-runner" / "core"
    core_str = str(core)
    if core_str not in sys.path:
        sys.path.insert(0, core_str)
    spec = importlib.util.spec_from_file_location("flow_runner", core / "flow_runner.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class FlowAssetsContractTests(unittest.TestCase):
    def test_flows_tree_restored_from_baseline(self) -> None:
        root = _repo_root()
        self.assertTrue((root / "flows" / "migration_map.json").is_file())
        self.assertTrue((root / "flows" / "rules" / "detail_panel_strict_v1.json").is_file())
        self.assertTrue((root / "flows" / "fragments" / "common" / "new_game_enter_world.json").is_file())
        self.assertTrue((root / "flows" / "fragments" / "common" / "navigate_to_target.json").is_file())
        self.assertTrue((root / "flows" / "internal" / "contract_force_fail_invalid_scene.json").is_file())
        gameplay = root / "flows" / "suites" / "regression" / "gameplay"
        self.assertTrue(gameplay.is_dir())
        flows = sorted(gameplay.glob("*.json"))
        self.assertGreaterEqual(len(flows), 15, msg="regression gameplay suite 文件数量异常")

    def test_regression_flow_step_ids_have_chat_templates(self) -> None:
        root = _repo_root()
        tpl_path = root / "tools" / "game-test-runner" / "mcp" / "chat_progress_templates.json"
        self.assertTrue(tpl_path.is_file(), msg="chat_progress_templates.json 必须存在")
        payload = json.loads(tpl_path.read_text(encoding="utf-8"))
        self.assertIsInstance(payload, dict)
        raw_step_map = payload.get("step_map")
        self.assertIsInstance(raw_step_map, dict)
        step_keys = {str(k).strip().lower() for k in raw_step_map}

        flow_runner = _load_flow_runner(root)
        from flow_parser import parse_flow_file  # noqa: PLC0415 — 需在 sys.path 注入后导入

        reg_dir = root / "flows" / "suites" / "regression" / "gameplay"
        missing_by_flow: dict[str, list[str]] = {}
        for path in sorted(reg_dir.glob("*.json")):
            flow = parse_flow_file(path)
            expanded = flow_runner._expand_steps(flow, path)
            missing: list[str] = []
            for step in expanded:
                if not isinstance(step, dict):
                    continue
                action = str(step.get("action", "")).strip()
                if not action:
                    continue
                sid = str(step.get("id", "")).strip().lower()
                if not sid:
                    continue
                if sid not in step_keys:
                    missing.append(sid)
            if missing:
                missing_by_flow[path.relative_to(root).as_posix()] = sorted(set(missing))

        self.assertEqual(
            missing_by_flow,
            {},
            msg=f"以下 flow 的步骤 id 未出现在 chat_progress_templates.json 的 step_map 中: {missing_by_flow}",
        )


if __name__ == "__main__":
    unittest.main()
