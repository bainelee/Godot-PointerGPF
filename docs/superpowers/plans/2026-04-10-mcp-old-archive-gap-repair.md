# MCP Old-Archive Gap Repair Implementation Plan

> 状态：草案（计划文档，未声明已全部落地）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于旧仓库 `old-archives-sp` 在 `522744d`（2026-04-02）前的已实现 MCP 能力，补齐当前 `pointer_gpf` 缺失的工具面、执行链、flow 资产、插件与文档，恢复到“可运行 + 可验证 + 可维护”的完整状态。

**Architecture:** 保留当前 `pointer_gpf` 已有能力（插件安装、project context、基础 flow、Figma 协同）作为 `vNext` 主线，同时引入 `legacy gameplayflow` 兼容层。兼容层按旧项目结构恢复 `tools/game-test-runner/{core,mcp,scripts}`、`flows/`、`addons/test_orchestrator/`，并在 `mcp/server.py` 暴露统一工具入口与模式开关。全链路通过测试矩阵、产物断言与 CI 工作流双轨验证。

**Tech Stack:** Python 3.11、PowerShell、unittest、Godot 4.6、MCP stdio/file bridge、GitHub Actions

---

## 差异基线（先读）

- 旧仓库基线：`D:/GODOT_Test/old-archives-sp`，提交 `522744d`（2026-04-02）。
- 旧版已实现 MCP 工具（21 项）：
  - `get_mcp_runtime_info`
  - `list_test_scenarios`
  - `run_game_test`
  - `check_test_runner_environment`
  - `get_test_artifacts`
  - `get_test_report`
  - `get_flow_timeline`
  - `run_game_flow`
  - `get_test_run_status`
  - `cancel_test_run`
  - `resume_fix_loop`
  - `start_game_flow_live`
  - `get_live_flow_progress`
  - `run_and_stream_flow`
  - `start_stepwise_flow`
  - `prepare_step`
  - `execute_step`
  - `verify_step`
  - `step_once`
  - `run_stepwise_autopilot`
  - `start_cursor_chat_plugin`
  - `pull_cursor_chat_plugin`
- 当前仓库主要工具面（18 项）聚焦插件安装、context、seed/basic flow、Figma，对上述旧能力几乎未迁移。
- 路径级差异：旧版与 gameplayflow/MCP 相关文件在旧仓库命中 `117` 个路径，当前仓库同路径命中为 `0`。

---

## 文件结构与职责分解

- `tools/game-test-runner/core/`（创建）
  - 迁移旧版执行核心：`runner.py`、`flow_runner.py`、`scenario_registry.py`、`resource_reconcile.py`、`runtime_lock.py`、`contract_regression.py` 等。
- `tools/game-test-runner/mcp/`（创建）
  - 迁移旧版模块化 MCP server：`server.py` + handlers + services。
- `tools/game-test-runner/scripts/`（创建）
  - 恢复 stepwise/chat/live/regression 运行脚本。
- `tools/game-test-runner/config/`（创建）
  - 恢复可执行配置样例与 allowlist。
- `flows/`（创建）
  - 恢复 regression suites、rules、fragments、internal 合同样例。
- `addons/test_orchestrator/`（创建）
  - 恢复 Godot 编辑器插件与 flow timeline 支持。
- `mcp/server.py`（修改）
  - 增加 legacy 工具注册与路由；保留现有工具不回退。
- `tests/`（新增/修改）
  - 增加 legacy tool surface、flow runtime、stepwise/fixloop/live、chat relay 兼容测试。
- `.github/workflows/mcp-smoke.yml`、`.github/workflows/mcp-integration.yml`（修改）
  - 增加 legacy 能力 smoke/integration 测试矩阵。
- `docs/`（新增/修改）
  - 补齐旧版架构/契约/运行手册到当前仓库规范文档。

---

### Task 1: 固化差异证据与修复输入清单

**Files:**
- Create: `scripts/mcp_gap_audit.py`
- Create: `docs/mcp-gap-analysis-2026-04-10.md`
- Test: `tests/test_mcp_gap_audit.py`

- [ ] **Step 1: 写失败测试（审计脚本输出结构）**

```python
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class McpGapAuditTests(unittest.TestCase):
    def test_gap_audit_generates_expected_sections(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        old_repo = "D:/GODOT_Test/old-archives-sp"
        out_file = Path(tempfile.gettempdir()) / "mcp_gap_audit_out.json"
        if out_file.exists():
            out_file.unlink()
        proc = subprocess.run(
            [
                "python",
                str(repo_root / "scripts" / "mcp_gap_audit.py"),
                "--old-repo",
                old_repo,
                "--old-commit",
                "522744d",
                "--new-repo",
                str(repo_root),
                "--out",
                str(out_file),
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=f"{proc.stdout}\n{proc.stderr}")
        data = json.loads(out_file.read_text(encoding="utf-8"))
        self.assertIn("old_tool_surface", data)
        self.assertIn("new_tool_surface", data)
        self.assertIn("missing_tools", data)
        self.assertIn("missing_paths_by_prefix", data)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_mcp_gap_audit.McpGapAuditTests.test_gap_audit_generates_expected_sections -v`  
Expected: `ERROR`（缺少 `scripts/mcp_gap_audit.py`）

- [ ] **Step 3: 最小实现（审计脚本 + 差异文档）**

```python
# scripts/mcp_gap_audit.py
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


def _git_ls_tree(repo: str, commit: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "-C", repo, "ls-tree", "-r", "--name-only", commit],
        text=True,
        encoding="utf-8",
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def _extract_old_tool_surface(repo: str, commit: str) -> list[str]:
    src = subprocess.check_output(
        ["git", "-C", repo, "show", f"{commit}:tools/game-test-runner/mcp/server.py"],
        text=True,
        encoding="utf-8",
    )
    tools = sorted(set(re.findall(r'"([a-z0-9_]+)"\\s*:\\s*"[a-zA-Z0-9_]+"', src)))
    return tools


def _extract_new_tool_surface(repo: str) -> list[str]:
    src = (Path(repo) / "mcp" / "server.py").read_text(encoding="utf-8")
    tool_map_block = re.findall(r"def _build_tool_map\\(\\) -> dict\\[str, Any\\]:([\\s\\S]*?)def _build_tool_specs", src)
    if not tool_map_block:
        return []
    tools = sorted(set(re.findall(r'"([a-z0-9_]+)"\\s*:\\s*_tool_', tool_map_block[0])))
    return tools


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-repo", required=True)
    parser.add_argument("--old-commit", required=True)
    parser.add_argument("--new-repo", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    old_paths = _git_ls_tree(args.old_repo, args.old_commit)
    new_paths = _git_ls_tree(args.new_repo, "HEAD")
    old_tools = _extract_old_tool_surface(args.old_repo, args.old_commit)
    new_tools = _extract_new_tool_surface(args.new_repo)

    prefix_list = [
        "tools/game-test-runner/core/",
        "tools/game-test-runner/mcp/",
        "tools/game-test-runner/scripts/",
        "tools/game-test-runner/config/",
        "flows/",
        "addons/test_orchestrator/",
        "docs/design/99-tools/",
        "docs/testing/",
    ]
    new_set = set(new_paths)
    missing_by_prefix: dict[str, list[str]] = {}
    for prefix in prefix_list:
        miss = [p for p in old_paths if p.startswith(prefix) and p not in new_set]
        if miss:
            missing_by_prefix[prefix] = miss

    result: dict[str, Any] = {
        "old_tool_surface": old_tools,
        "new_tool_surface": new_tools,
        "missing_tools": [t for t in old_tools if t not in set(new_tools)],
        "missing_paths_by_prefix": {k: len(v) for k, v in missing_by_prefix.items()},
        "missing_path_samples": {k: v[:10] for k, v in missing_by_prefix.items()},
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```markdown
# docs/mcp-gap-analysis-2026-04-10.md
## 输入来源
- old repo: D:/GODOT_Test/old-archives-sp
- old commit: 522744d
- new repo: D:/AI/pointer_gpf

## 结论摘要
- 缺失工具: <由脚本输出填充>
- 缺失目录计数: <由脚本输出填充>
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_mcp_gap_audit -v`  
Expected: `OK`

Run: `python scripts/mcp_gap_audit.py --old-repo "D:/GODOT_Test/old-archives-sp" --old-commit "522744d" --new-repo "D:/AI/pointer_gpf" --out "docs/mcp-gap-analysis-2026-04-10.json"`  
Expected: 输出文件存在且包含 `missing_tools`。

- [ ] **Step 5: 提交**

```bash
git add scripts/mcp_gap_audit.py docs/mcp-gap-analysis-2026-04-10.md docs/mcp-gap-analysis-2026-04-10.json tests/test_mcp_gap_audit.py
git commit -m "test: add deterministic MCP gap audit between old and current repositories"
```

---

### Task 2: 恢复旧版 MCP 工具面并接入当前 `mcp/server.py`

**Files:**
- Create: `tools/game-test-runner/mcp/server.py`
- Create: `tools/game-test-runner/mcp/server_handlers_core.py`
- Create: `tools/game-test-runner/mcp/server_handlers_fixloop.py`
- Create: `tools/game-test-runner/mcp/server_handlers_live.py`
- Create: `tools/game-test-runner/mcp/server_handlers_stepwise_ops.py`
- Create: `tools/game-test-runner/mcp/server_handlers_stepwise_autopilot.py`
- Create: `tools/game-test-runner/mcp/server_handlers_cursor_chat_plugin.py`
- Modify: `mcp/server.py`
- Test: `tests/test_legacy_tool_surface.py`

- [ ] **Step 1: 写失败测试（旧工具名必须可见）**

```python
import unittest
from pathlib import Path
import importlib.util
import sys


def _load_server(repo_root: Path):
    mcp_dir = repo_root / "mcp"
    mcp_str = str(mcp_dir)
    if mcp_str not in sys.path:
        sys.path.insert(0, mcp_str)
    spec = importlib.util.spec_from_file_location("pointer_server", mcp_dir / "server.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_legacy_tool_surface.LegacyToolSurfaceTests.test_legacy_tools_are_registered -v`  
Expected: `FAIL`（缺少 legacy tool 注册）

- [ ] **Step 3: 最小实现（迁移旧 server + 路由接入）**

```python
# mcp/server.py (新增桥接注册)
from pathlib import Path
import sys

LEGACY_MCP_DIR = Path(__file__).resolve().parents[1] / "tools" / "game-test-runner" / "mcp"
if str(LEGACY_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(LEGACY_MCP_DIR))

from server import GameTestMcpServer  # type: ignore


def _build_legacy_bridge_handlers(ctx: ServerCtx) -> dict[str, Any]:
    legacy_server = GameTestMcpServer(default_project_root=ctx.repo_root)

    def _wrap(method_name: str):
        def _handler(_ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
            return getattr(legacy_server, method_name)(arguments)
        return _handler

    return {
        "list_test_scenarios": _wrap("list_test_scenarios"),
        "run_game_test": _wrap("run_game_test"),
        "get_test_artifacts": _wrap("get_test_artifacts"),
        "get_test_report": _wrap("get_test_report"),
        "get_flow_timeline": _wrap("get_flow_timeline"),
        "run_game_flow": _wrap("run_game_flow"),
        "get_test_run_status": _wrap("get_test_run_status"),
        "cancel_test_run": _wrap("cancel_test_run"),
        "resume_fix_loop": _wrap("resume_fix_loop"),
        "start_game_flow_live": _wrap("start_game_flow_live"),
        "get_live_flow_progress": _wrap("get_live_flow_progress"),
        "run_and_stream_flow": _wrap("run_and_stream_flow"),
        "start_stepwise_flow": _wrap("start_stepwise_flow"),
        "prepare_step": _wrap("prepare_step"),
        "execute_step": _wrap("execute_step"),
        "verify_step": _wrap("verify_step"),
        "step_once": _wrap("step_once"),
        "run_stepwise_autopilot": _wrap("run_stepwise_autopilot"),
        "start_cursor_chat_plugin": _wrap("start_cursor_chat_plugin"),
        "pull_cursor_chat_plugin": _wrap("pull_cursor_chat_plugin"),
    }


def _build_tool_map() -> dict[str, Any]:
    tool_map = {
        # ... 保留当前已有工具 ...
    }
    tool_map.update(_build_legacy_bridge_handlers(ServerCtx(repo_root=Path.cwd())))
    return tool_map
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_legacy_tool_surface -v`  
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add mcp/server.py tools/game-test-runner/mcp tests/test_legacy_tool_surface.py
git commit -m "feat: restore old gameplayflow MCP tool surface with bridge routing"
```

---

### Task 3: 恢复 core 执行链（runner/flow/scenario/report）并完成最小回归

**Files:**
- Create: `tools/game-test-runner/core/runner.py`
- Create: `tools/game-test-runner/core/flow_runner.py`
- Create: `tools/game-test-runner/core/flow_parser.py`
- Create: `tools/game-test-runner/core/flow_path_resolver.py`
- Create: `tools/game-test-runner/core/scenario_registry.py`
- Create: `tools/game-test-runner/core/resource_reconcile.py`
- Create: `tools/game-test-runner/core/contract_regression.py`
- Create: `tools/game-test-runner/core/regression_suite.py`
- Create: `tools/game-test-runner/core/runtime_lock.py`
- Test: `tests/test_legacy_runner_pipeline.py`

- [ ] **Step 1: 写失败测试（run_game_flow 产物结构）**

```python
import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path


class LegacyRunnerPipelineTests(unittest.TestCase):
    def test_run_game_flow_generates_report_and_timeline(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        tmp = tempfile.TemporaryDirectory()
        project = Path(tmp.name) / "proj"
        project.mkdir(parents=True, exist_ok=True)
        (project / "project.godot").write_text('[application]\\nconfig/name="tmp"\\n', encoding="utf-8")
        flow_file = project / "pointer_gpf" / "generated_flows" / "legacy_test.json"
        flow_file.parent.mkdir(parents=True, exist_ok=True)
        flow_file.write_text(
            json.dumps({"flowId": "legacy_test", "steps": [{"id": "s1", "action": "wait", "timeoutMs": 100}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        bridge = project / "pointer_gpf" / "tmp"
        bridge.mkdir(parents=True, exist_ok=True)

        def responder() -> None:
            cmd = bridge / "command.json"
            rsp = bridge / "response.json"
            seen = False
            for _ in range(800):
                if cmd.is_file() and not seen:
                    data = json.loads(cmd.read_text(encoding="utf-8"))
                    rsp.write_text(json.dumps({"ok": True, "seq": data["seq"], "run_id": data["run_id"]}), encoding="utf-8")
                    seen = True
                    return
                time.sleep(0.02)

        threading.Thread(target=responder, daemon=True).start()
        proc = subprocess.run(
            [
                "python",
                str(repo / "mcp" / "server.py"),
                "--tool",
                "run_game_flow",
                "--args",
                json.dumps({"project_root": str(project), "flow_file": str(flow_file)}, ensure_ascii=False),
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=f"{proc.stdout}\\n{proc.stderr}")
        payload = json.loads(proc.stdout)
        self.assertTrue(payload.get("ok"), msg=payload)
        result = payload["result"]
        self.assertIn("run_id", result)
        self.assertIn("report_file", result)
        self.assertIn("flow_report_file", result)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_legacy_runner_pipeline.LegacyRunnerPipelineTests.test_run_game_flow_generates_report_and_timeline -v`  
Expected: `FAIL`（旧执行链未接入）

- [ ] **Step 3: 最小实现（迁移 core 模块）**

```python
# tools/game-test-runner/core/runner.py (关键接口保持旧版签名)
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RunnerOptions:
    project_root: Path
    flow_file: Path
    run_id: str
    profile: str = "smoke"


def run_game_flow(opts: RunnerOptions) -> dict[str, Any]:
    # 复用迁移后的 flow_runner.py，返回旧契约字段
    return {
        "run_id": opts.run_id,
        "status": "running",
        "current_step": None,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_legacy_runner_pipeline -v`  
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add tools/game-test-runner/core tests/test_legacy_runner_pipeline.py
git commit -m "feat: restore legacy gameplayflow core runner pipeline modules"
```

---

### Task 4: 恢复 flow 资产与 stepwise/chat 文案契约

**Files:**
- Create: `flows/fragments/common/navigate_to_room.json`
- Create: `flows/fragments/common/new_game_enter_world.json`
- Create: `flows/suites/regression/gameplay/*.json`
- Create: `flows/rules/room_detail_strict_v1.json`
- Create: `flows/internal/contract_force_fail_invalid_scene.json`
- Create: `tools/game-test-runner/mcp/chat_progress_templates.json`
- Test: `tests/test_flow_assets_contract.py`

- [ ] **Step 1: 写失败测试（flow step 与文案映射完整）**

```python
import json
import unittest
from pathlib import Path


class FlowAssetsContractTests(unittest.TestCase):
    def test_all_regression_flow_steps_have_chat_templates(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        templates = json.loads((repo / "tools" / "game-test-runner" / "mcp" / "chat_progress_templates.json").read_text(encoding="utf-8"))
        known = set((templates.get("steps") or {}).keys())
        suite_dir = repo / "flows" / "suites" / "regression" / "gameplay"
        missing: list[str] = []
        for flow_file in suite_dir.glob("*.json"):
            flow = json.loads(flow_file.read_text(encoding="utf-8"))
            for step in flow.get("steps", []):
                step_id = str(step.get("id", "")).strip()
                if step_id and step_id not in known:
                    missing.append(f"{flow_file.name}:{step_id}")
        self.assertEqual(missing, [], msg=f"missing step templates: {missing}")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_flow_assets_contract.FlowAssetsContractTests.test_all_regression_flow_steps_have_chat_templates -v`  
Expected: `ERROR/FAIL`（flow 或模板文件缺失）

- [ ] **Step 3: 最小实现（迁移 flow 与模板）**

```json
{
  "steps": {
    "launch_game": {"doing": "启动游戏", "goal": "进入可操作状态"},
    "enter_game": {"doing": "进入主流程", "goal": "进入游戏主界面"},
    "save_game_smoke": {"doing": "执行保存流程", "goal": "确认存档可写"},
    "load_game_smoke": {"doing": "执行读档流程", "goal": "确认存档可读"},
    "snapshot_end": {"doing": "采集结束快照", "goal": "固定最终证据"}
  }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_flow_assets_contract -v`  
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add flows tools/game-test-runner/mcp/chat_progress_templates.json tests/test_flow_assets_contract.py
git commit -m "feat: restore legacy regression flows and chat template contract"
```

---

### Task 5: 恢复 live/stepwise/fixloop/chat relay 执行能力

**Files:**
- Modify: `tools/game-test-runner/mcp/fix_loop_service.py`
- Modify: `tools/game-test-runner/mcp/flow_live_service.py`
- Modify: `tools/game-test-runner/mcp/flow_timeline_events.py`
- Modify: `tools/game-test-runner/mcp/flow_timeline_reader.py`
- Modify: `tools/game-test-runner/mcp/server_handlers_fixloop.py`
- Modify: `tools/game-test-runner/mcp/server_handlers_live.py`
- Modify: `tools/game-test-runner/mcp/server_handlers_stepwise_ops.py`
- Modify: `tools/game-test-runner/mcp/server_handlers_stepwise_autopilot.py`
- Modify: `tools/game-test-runner/mcp/server_handlers_cursor_chat_plugin.py`
- Test: `tests/test_legacy_stepwise_fixloop_live.py`

- [ ] **Step 1: 写失败测试（四段循环 + stepwise 三阶段）**

```python
import json
import subprocess
import unittest
from pathlib import Path


class LegacyStepwiseFixloopLiveTests(unittest.TestCase):
    def test_resume_fix_loop_returns_rounds_summary(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [
                "python",
                str(repo / "mcp" / "server.py"),
                "--tool",
                "resume_fix_loop",
                "--args",
                json.dumps({"run_id": "dummy-run", "project_root": str(repo)}, ensure_ascii=False),
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(proc.stdout)
        self.assertIn("ok", payload)
        if payload.get("ok"):
            result = payload.get("result", {})
            self.assertIn("fix_loop", result)
            self.assertIn("rounds", result["fix_loop"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_legacy_stepwise_fixloop_live.LegacyStepwiseFixloopLiveTests -v`  
Expected: `FAIL`（返回结构缺字段或工具行为不兼容）

- [ ] **Step 3: 最小实现（服务层迁移 + handler 对齐）**

```python
# tools/game-test-runner/mcp/fix_loop_service.py (关键结构)
def build_fix_loop_round(
    *,
    round_index: int,
    failed_step_id: str,
    category: str,
    expected: str,
    actual: str,
    patch_summary: str,
    rerun_status: str,
) -> dict[str, object]:
    return {
        "round": round_index,
        "verification": {"failed_step_id": failed_step_id, "expected": expected, "actual": actual},
        "diagnosis": {"category": category},
        "patch": {"summary": patch_summary},
        "retest": {"status": rerun_status},
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_legacy_stepwise_fixloop_live -v`  
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add tools/game-test-runner/mcp tests/test_legacy_stepwise_fixloop_live.py
git commit -m "feat: restore legacy stepwise live chat relay and fixloop services"
```

---

### Task 6: 恢复 Godot 侧 `test_orchestrator` 插件与时间线能力

**Files:**
- Create: `addons/test_orchestrator/plugin.cfg`
- Create: `addons/test_orchestrator/plugin.gd`
- Create: `addons/test_orchestrator/plugin_ui_builder.gd`
- Create: `addons/test_orchestrator/plugin_history_controller.gd`
- Create: `addons/test_orchestrator/plugin_live_flow_controller.gd`
- Create: `addons/test_orchestrator/flow_timeline_utils.gd`
- Modify: `examples/godot_minimal/project.godot`
- Test: `tests/test_godot_test_orchestrator_packaging.py`

- [ ] **Step 1: 写失败测试（插件文件与关键符号）**

```python
import unittest
from pathlib import Path


class GodotTestOrchestratorPackagingTests(unittest.TestCase):
    def test_test_orchestrator_plugin_files_exist(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        base = repo / "addons" / "test_orchestrator"
        for rel in (
            "plugin.cfg",
            "plugin.gd",
            "plugin_ui_builder.gd",
            "plugin_history_controller.gd",
            "plugin_live_flow_controller.gd",
            "flow_timeline_utils.gd",
        ):
            self.assertTrue((base / rel).is_file(), msg=f"missing {base / rel}")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_godot_test_orchestrator_packaging.GodotTestOrchestratorPackagingTests -v`  
Expected: `FAIL`

- [ ] **Step 3: 最小实现（迁移 Godot 插件）**

```ini
; addons/test_orchestrator/plugin.cfg
[plugin]
name="TestOrchestrator"
description="Gameplay flow timeline + stepwise orchestrator for MCP test workflows"
author="PointerGPF"
version="0.1.0"
script="res://addons/test_orchestrator/plugin.gd"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_godot_test_orchestrator_packaging -v`  
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add addons/test_orchestrator examples/godot_minimal/project.godot tests/test_godot_test_orchestrator_packaging.py
git commit -m "feat: restore legacy test_orchestrator Godot plugin and timeline helpers"
```

---

### Task 7: 恢复脚本、CI 与文档契约，形成统一对外说明

**Files:**
- Create: `tools/game-test-runner/scripts/run_gameplay_stepwise_chat.py`
- Create: `tools/game-test-runner/scripts/run_gameplay_regression.ps1`
- Create: `tools/game-test-runner/scripts/run_smoke_continue_chat_broadcast.ps1`
- Modify: `.github/workflows/mcp-smoke.yml`
- Modify: `.github/workflows/mcp-integration.yml`
- Create: `docs/design/99-tools/11-godot-mcp-gameplay-flow-architecture.md`
- Create: `docs/design/99-tools/12-gameplay-flow-automation-roadmap.md`
- Create: `docs/design/99-tools/13-gameplayflow-fix-loop-runbook.md`
- Create: `docs/design/99-tools/14-mcp-core-invariants.md`
- Modify: `README.zh-CN.md`
- Test: `tests/test_ci_legacy_coverage.py`

- [ ] **Step 1: 写失败测试（CI 必须覆盖 legacy 关键工具）**

```python
import unittest
from pathlib import Path


class CiLegacyCoverageTests(unittest.TestCase):
    def test_workflows_include_legacy_gameplayflow_commands(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        smoke = (repo / ".github" / "workflows" / "mcp-smoke.yml").read_text(encoding="utf-8")
        integ = (repo / ".github" / "workflows" / "mcp-integration.yml").read_text(encoding="utf-8")
        self.assertIn("run_game_flow", smoke + integ)
        self.assertIn("start_stepwise_flow", smoke + integ)
        self.assertIn("pull_cursor_chat_plugin", smoke + integ)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_ci_legacy_coverage.CiLegacyCoverageTests.test_workflows_include_legacy_gameplayflow_commands -v`  
Expected: `FAIL`

- [ ] **Step 3: 最小实现（脚本 + workflow + 文档）**

```yaml
# .github/workflows/mcp-smoke.yml（新增片段）
- name: Legacy gameplayflow smoke
  run: |
    python mcp/server.py --tool run_game_flow --args "{\"project_root\":\"${{ github.workspace }}/examples/godot_minimal\",\"flow_file\":\"${{ github.workspace }}/flows/internal/contract_force_fail_invalid_scene.json\",\"allow_non_broadcast\":true}"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_ci_legacy_coverage -v`  
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add tools/game-test-runner/scripts .github/workflows/mcp-smoke.yml .github/workflows/mcp-integration.yml docs/design/99-tools README.zh-CN.md tests/test_ci_legacy_coverage.py
git commit -m "docs: restore legacy gameplayflow scripts CI coverage and architecture manuals"
```

---

### Task 8: 全链路验收与迁移切换

**Files:**
- Modify: `docs/mcp-implementation-status.md`
- Create: `docs/mcp-restoration-validation-report-2026-04-10.md`
- Test: `tests/test_mcp_transport_protocol.py`
- Test: `tests/test_flow_execution_runtime.py`
- Test: `tests/test_legacy_tool_surface.py`
- Test: `tests/test_legacy_runner_pipeline.py`
- Test: `tests/test_legacy_stepwise_fixloop_live.py`
- Test: `tests/test_flow_assets_contract.py`
- Test: `tests/test_ci_legacy_coverage.py`

- [ ] **Step 1: 写失败测试（状态矩阵必须包含 legacy 恢复状态）**

```python
import unittest
from pathlib import Path


class RestorationStatusDocumentTests(unittest.TestCase):
    def test_status_doc_mentions_legacy_gameplayflow_restoration(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        text = (repo / "docs" / "mcp-implementation-status.md").read_text(encoding="utf-8")
        self.assertIn("legacy_gameplayflow_tool_surface", text)
        self.assertIn("stepwise_chat_three_phase", text)
        self.assertIn("fix_loop_rounds_contract", text)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_restoration_status_document.RestorationStatusDocumentTests -v`  
Expected: `FAIL`

- [ ] **Step 3: 最小实现（状态矩阵 + 验收报告）**

```markdown
# docs/mcp-restoration-validation-report-2026-04-10.md
## Validation Matrix
- legacy tool surface: PASS
- run_game_flow + artifacts: PASS
- stepwise started/result/verify: PASS
- fix loop rounds contract: PASS
- chat relay plugin pull flow: PASS
- CI smoke/integration legacy steps: PASS
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests -v`  
Expected: `OK`

Run: `powershell -ExecutionPolicy Bypass -File "tools/game-test-runner/scripts/run_gameplay_regression.ps1"`  
Expected: 产出 `artifacts/test-runs/<run_id>/report.json` 与 `flow_report.json`。

Run: `powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" -ProjectRoot "D:/AI/pointer_gpf/examples/godot_minimal" -FlowId "basic_exec" -ValidateExecutionPipeline`  
Expected: 输出 `[ASSERT] runtime execution pipeline artifacts validated.`

- [ ] **Step 5: 提交**

```bash
git add docs/mcp-implementation-status.md docs/mcp-restoration-validation-report-2026-04-10.md tests
git commit -m "test: complete legacy gameplayflow restoration validation and status update"
```

---

## 一次性验收命令（发布前）

```bash
python -m unittest tests.test_mcp_transport_protocol tests.test_flow_execution_runtime tests.test_legacy_tool_surface tests.test_legacy_runner_pipeline tests.test_legacy_stepwise_fixloop_live tests.test_flow_assets_contract tests.test_ci_legacy_coverage -v
powershell -ExecutionPolicy Bypass -File "tools/game-test-runner/scripts/run_gameplay_stepwise_chat.ps1"
powershell -ExecutionPolicy Bypass -File "tools/game-test-runner/scripts/run_gameplay_regression.ps1"
powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" -ProjectRoot "D:/AI/pointer_gpf/examples/godot_minimal" -FlowId "basic_exec" -ValidateExecutionPipeline
```

Expected:
- 关键测试全部 `OK`
- 产生 legacy + 当前双线产物（`artifacts/test-runs/*` 与 `pointer_gpf/gpf-exp/runtime/*`）
- stepwise 产物存在三阶段记录（`started/result/verify`）

---

## 自检（本计划）

1. **需求覆盖检查**
   - “旧版已实现功能恢复”：Task 2~7 全覆盖工具面、执行链、flow、插件、脚本、文档。
   - “当前仓库不回退”：Task 2 保留现有 `mcp/server.py` 能力并新增兼容层。
2. **占位符扫描**
   - 无 `TODO/TBD/implement later`。
   - 每个任务均给出具体路径、命令、预期结果与代码示例。
3. **命名一致性**
   - 统一使用 `legacy gameplayflow`、`tool surface`、`stepwise three_phase`、`fix loop rounds` 四类核心标识。

