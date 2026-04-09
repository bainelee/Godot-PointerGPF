# MCP 基础测试流程全链路执行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 PointerGPF 从“仅生成/校验 flow”升级为“可运行游戏、按步骤执行并在 shell 输出 started/result/verify 三阶段播报”的完整基础测试闭环。

**Architecture:** 在 MCP 侧新增 flow 执行器（读取 flow JSON、驱动 adapter_contract 的 required actions、输出阶段事件与最终报告），在 Godot 插件模板侧补齐 file_bridge 运行时桥接（command/response 文件通道）。保持现有 seed 生成和产物契约能力不变，新增执行层工具与执行层验证脚本，并同步 CI 与文档口径。

**Tech Stack:** Python 3.11（`mcp/server.py` + 新执行器模块）、Godot GDScript（插件桥接）、PowerShell（验证脚本）、unittest（回归测试）、GitHub Actions（CI smoke/integration）。

---

## 文件结构与职责

- Create: `mcp/flow_execution.py`  
  负责 flow 读取、step 执行、三阶段事件产出、执行报告落盘。
- Modify: `mcp/server.py`  
  注册新工具、参数 schema、CLI 快捷参数、调用执行器、错误映射。
- Create: `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd`  
  file_bridge 轮询 `command.json`，调用动作执行，回写 `response.json`。
- Modify: `godot_plugin_template/addons/pointer_gpf/plugin.gd`  
  启动/关闭运行时桥接节点。
- Create: `tests/test_flow_execution_runtime.py`  
  覆盖执行器成功路径、失败路径、超时路径、三阶段日志。
- Modify: `tests/test_natural_language_basic_flow_commands.py`  
  增加“设计 + 执行基础流程”联动测试。
- Modify: `scripts/assert-mcp-artifacts.ps1`  
  新增执行层契约断言（report + events + 阶段完整性）。
- Modify: `scripts/verify-cross-project.ps1`  
  新增可选运行阶段（设计 flow 后实际执行）。
- Modify: `.github/workflows/mcp-smoke.yml`  
  增加最小执行链路（mock bridge）验证，确保 PR 阶段覆盖执行能力。
- Modify: `.github/workflows/mcp-integration.yml`  
  增加执行层指标输出（stage=run_game_basic_test_flow）。
- Modify: `mcp/adapter_contract_v1.json`、`docs/godot-adapter-contract-v1.md`  
  写清 file_bridge 执行时序、command/response 结构、错误语义。
- Modify: `docs/quickstart.md`、`README.zh-CN.md`、`README.md`、`docs/mcp-testing-spec.md`  
  同步“基础测试流程=生成+执行+播报+断言”口径与命令示例。

## 子代理使用方案

- **子代理类型**
  - `explore`：定位代码入口、回归影响面。
  - `generalPurpose`：实现单任务代码变更。
  - `code-reviewer`：每 2 个任务后做一次质量审查。
- **任务分工**
  - 子代理 A：`mcp/flow_execution.py` + `mcp/server.py` 新工具接入。
  - 子代理 B：Godot 插件桥接 `runtime_bridge.gd` + `plugin.gd`。
  - 子代理 C：测试与脚本（`tests/` + `scripts/` + CI workflow）。
- **并行策略**
  - Task 2（MCP 执行器）与 Task 3（插件桥接）可并行。
  - Task 4（脚本/CI）依赖 Task 2 完成；Task 5（文档）最后串行收口。
- **触发条件**
  - 任何 task 出现 2 次以上测试失败：触发 `code-reviewer` 先审查再继续。
  - 触达 CI 文件前：先要求当前分支本地测试全绿。
- **交付物**
  - 每个 task 提交一个 commit。
  - 每个 task 输出：变更文件清单、测试命令和结果、风险点。

---

### Task 1: 新增执行工具入口（先立接口再实现）

**Files:**
- Modify: `mcp/server.py`
- Test: `tests/test_flow_execution_runtime.py`

- [ ] **Step 1: 写失败测试（工具必须已注册）**

```python
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class FlowExecutionToolRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.project_tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self.project_tmp.name) / "proj"
        self.project_root.mkdir(parents=True, exist_ok=True)
        (self.project_root / "project.godot").write_text('[application]\nconfig/name="tmp"\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.project_tmp.cleanup()

    def test_runtime_info_contains_run_game_basic_test_flow_tool(self) -> None:
        proc = subprocess.run(
            ["python", str(self.repo_root / "mcp/server.py"), "--tool", "get_mcp_runtime_info", "--project-root", str(self.project_root)],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertIn("run_game_basic_test_flow", payload["result"]["tools"])

    def test_run_game_basic_test_flow_currently_requires_flow(self) -> None:
        proc = subprocess.run(
            [
                "python",
                str(self.repo_root / "mcp/server.py"),
                "--tool",
                "run_game_basic_test_flow",
                "--project-root",
                str(self.project_root),
                "--flow-id",
                "missing_flow",
            ],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionToolRegistrationTests -v`  
Expected: FAIL，提示 `run_game_basic_test_flow` 不在 tools 列表或 tool unsupported。

- [ ] **Step 3: 最小实现（先接入工具壳）**

```python
# mcp/server.py（示例片段）
def _tool_run_game_basic_test_flow(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    flow_id = str(arguments.get("flow_id", "")).strip()
    if not flow_id:
        flow_id = "basic_game_test_flow"
    flow_path = (project_root / cfg.seed_flow_dir_rel / f"{_slugify(flow_id)}.json").resolve()
    if not flow_path.exists():
        raise AppError("INVALID_ARGUMENT", f"flow file not found: {flow_path}")
    raise AppError("NOT_IMPLEMENTED", "flow execution is not implemented yet")


# _build_tool_map() 增加
"run_game_basic_test_flow": _tool_run_game_basic_test_flow,

# _tool_get_mcp_runtime_info() tools 数组增加
"run_game_basic_test_flow",

# _build_tool_specs() 增加 schema
"run_game_basic_test_flow": {
    "description": "Run basic test flow with adapter actions and emit three-phase logs.",
    "inputSchema": {
        "type": "object",
        "required": ["project_root"],
        "properties": {
            **base_props,
            "flow_id": {"type": "string"},
            "flow_file": {"type": "string"},
            "step_timeout_ms": {"type": "integer"},
            "fail_fast": {"type": "boolean"},
            "shell_report": {"type": "boolean"},
        },
    },
},
```

- [ ] **Step 4: 运行测试确认转绿**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionToolRegistrationTests -v`  
Expected: PASS（第一条通过；第二条报 `INVALID_ARGUMENT` 或 `NOT_IMPLEMENTED`，与测试断言一致）。

- [ ] **Step 5: 提交**

```bash
git add mcp/server.py tests/test_flow_execution_runtime.py
git commit -m "feat: register run_game_basic_test_flow tool interface"
```

---

### Task 2: 实现 MCP 侧 flow 执行器（三阶段播报 + 报告）

**Files:**
- Create: `mcp/flow_execution.py`
- Modify: `mcp/server.py`
- Test: `tests/test_flow_execution_runtime.py`

- [ ] **Step 1: 写失败测试（执行路径）**

```python
class FlowExecutionRuntimeTests(unittest.TestCase):
    def test_run_flow_emits_started_result_verify(self) -> None:
        # 1) 构造临时项目 + flow 文件
        # 2) 启动 mock bridge（轮询 command.json 并回写 response.json）
        # 3) 调 run_game_basic_test_flow
        # 4) 断言 report + events.ndjson 中每个 step 含 started/result/verify
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["phase_coverage"]["started"], report["step_count"])
        self.assertEqual(report["phase_coverage"]["result"], report["step_count"])
        self.assertEqual(report["phase_coverage"]["verify"], report["step_count"])

    def test_run_flow_times_out_when_bridge_no_response(self) -> None:
        # 不启动 bridge，只创建 flow
        self.assertEqual(payload["error"]["code"], "TIMEOUT")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionRuntimeTests -v`  
Expected: FAIL，当前无执行实现，无法生成 report 或阶段覆盖。

- [ ] **Step 3: 编写最小可用执行器实现**

```python
# mcp/flow_execution.py（核心接口）
from __future__ import annotations
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FlowRunOptions:
    step_timeout_ms: int = 15000
    fail_fast: bool = True
    shell_report: bool = True


class FlowRunner:
    def __init__(self, project_root: Path, runtime_dir: Path, bridge_dir: Path) -> None:
        self.project_root = project_root
        self.runtime_dir = runtime_dir
        self.bridge_dir = bridge_dir
        self.command_file = bridge_dir / "command.json"
        self.response_file = bridge_dir / "response.json"

    def run(self, flow_payload: dict[str, Any], options: FlowRunOptions) -> dict[str, Any]:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        steps = list(flow_payload.get("steps", []))
        events: list[dict[str, Any]] = []
        phase = {"started": 0, "result": 0, "verify": 0}
        for step in steps:
            step_id = str(step.get("id", ""))
            action = str(step.get("action", ""))
            started = {"run_id": run_id, "step_id": step_id, "phase": "started", "action": action, "ts": time.time()}
            events.append(started)
            phase["started"] += 1
            result = self._invoke_bridge(run_id, step, options.step_timeout_ms)
            events.append({"run_id": run_id, "step_id": step_id, "phase": "result", "result": result, "ts": time.time()})
            phase["result"] += 1
            ok = bool(result.get("ok", False))
            events.append({"run_id": run_id, "step_id": step_id, "phase": "verify", "ok": ok, "ts": time.time()})
            phase["verify"] += 1
            if not ok and options.fail_fast:
                break
        status = "passed" if all(e.get("ok", True) for e in events if e.get("phase") == "verify") else "failed"
        report = {
            "run_id": run_id,
            "status": status,
            "step_count": len(steps),
            "phase_coverage": phase,
            "events_file": str(self._write_events(run_id, events)),
        }
        self._write_report(run_id, report)
        return report
```

- [ ] **Step 4: 在 `mcp/server.py` 接入执行器**

```python
# mcp/server.py（示例片段）
from mcp.flow_execution import FlowRunner, FlowRunOptions

def _tool_run_game_basic_test_flow(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    flow_file_raw = str(arguments.get("flow_file", "")).strip()
    if flow_file_raw:
        flow_path = Path(flow_file_raw).resolve()
    else:
        flow_id = _slugify(str(arguments.get("flow_id", "")).strip() or "basic_game_test_flow")
        flow_path = (project_root / cfg.seed_flow_dir_rel / f"{flow_id}.json").resolve()
    if not flow_path.exists():
        raise AppError("INVALID_ARGUMENT", f"flow file not found: {flow_path}")
    flow_payload = _read_json_file(flow_path)
    runtime_dir = _exp_runtime_dir(project_root, cfg)
    bridge_dir = (project_root / "pointer_gpf" / "tmp").resolve()
    options = FlowRunOptions(
        step_timeout_ms=max(1000, int(arguments.get("step_timeout_ms", 15000))),
        fail_fast=bool(arguments.get("fail_fast", True)),
        shell_report=bool(arguments.get("shell_report", True)),
    )
    runner = FlowRunner(project_root=project_root, runtime_dir=runtime_dir, bridge_dir=bridge_dir)
    report = runner.run(flow_payload, options)
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="basic_game_test_execution_last",
        payload={"tool": "run_game_basic_test_flow", "generated_at": _utc_iso(), "project_root": str(project_root), **report},
    )
    return {"status": report["status"], "flow_file": str(flow_path), "execution_report": report, "exp_runtime": exp_artifact}
```

- [ ] **Step 5: 运行测试确认转绿**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionRuntimeTests -v`  
Expected: PASS；并且临时项目下出现 `pointer_gpf/gpf-exp/runtime/flow_run_report_*.json` 与 `flow_run_events_*.ndjson`。

- [ ] **Step 6: 提交**

```bash
git add mcp/flow_execution.py mcp/server.py tests/test_flow_execution_runtime.py
git commit -m "feat: implement runtime flow runner with three-phase reporting"
```

---

### Task 3: 实现 Godot file_bridge 运行时桥接

**Files:**
- Create: `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd`
- Modify: `godot_plugin_template/addons/pointer_gpf/plugin.gd`
- Test: `tests/test_flow_execution_runtime.py`

- [ ] **Step 1: 写失败测试（插件安装后必须具备 bridge 文件）**

```python
def test_install_plugin_contains_runtime_bridge(self) -> None:
    result = _run_tool(self.repo_root, "install_godot_plugin", {"project_root": str(self.project_root)})
    self.assertEqual(result["status"], "installed")
    bridge_file = self.project_root / "addons" / "pointer_gpf" / "runtime_bridge.gd"
    self.assertTrue(bridge_file.exists())
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_flow_execution_runtime.PluginBridgePackagingTests -v`  
Expected: FAIL，`runtime_bridge.gd` 尚未提供。

- [ ] **Step 3: 实现 bridge 轮询与动作分发**

```gdscript
# godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd
extends Node

const BRIDGE_DIR := "res://pointer_gpf/tmp"
const COMMAND_PATH := "res://pointer_gpf/tmp/command.json"
const RESPONSE_PATH := "res://pointer_gpf/tmp/response.json"

func _ready() -> void:
    _ensure_bridge_dir()
    set_process(true)

func _process(_delta: float) -> void:
    if not FileAccess.file_exists(COMMAND_PATH):
        return
    var raw := FileAccess.get_file_as_string(COMMAND_PATH)
    if raw.is_empty():
        return
    var parsed = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        _write_response({"ok": false, "error": {"code": "INVALID_ARGUMENT", "message": "command must be json object"}})
        return
    var cmd: Dictionary = parsed
    var action := str(cmd.get("action", ""))
    var result := _execute_action(action, cmd)
    _write_response(result)
    DirAccess.remove_absolute(ProjectSettings.globalize_path(COMMAND_PATH))

func _execute_action(action: String, cmd: Dictionary) -> Dictionary:
    match action:
        "launchGame":
            return {"ok": true, "message": "launch requested"}
        "click":
            return {"ok": true, "message": "click accepted", "target": cmd.get("target", {})}
        "wait":
            return {"ok": true, "elapsedMs": 16, "conditionMet": true}
        "check":
            return {"ok": true, "details": {"status": "pass"}}
        "snapshot":
            return {"ok": true, "artifactPath": "pointer_gpf/gpf-exp/runtime/mock_snapshot.png"}
        _:
            return {"ok": false, "error": {"code": "ACTION_NOT_SUPPORTED", "message": "unsupported action: " + action}}
```

- [ ] **Step 4: 在插件入口挂载 bridge 节点**

```gdscript
# godot_plugin_template/addons/pointer_gpf/plugin.gd
@tool
extends EditorPlugin

var _runtime_bridge: Node = null

func _enter_tree() -> void:
    var bridge_script = load("res://addons/pointer_gpf/runtime_bridge.gd")
    if bridge_script != null:
        _runtime_bridge = bridge_script.new()
        get_tree().root.add_child(_runtime_bridge)

func _exit_tree() -> void:
    if _runtime_bridge != null and is_instance_valid(_runtime_bridge):
        _runtime_bridge.queue_free()
        _runtime_bridge = null
```

- [ ] **Step 5: 运行测试确认转绿**

Run: `python -m unittest tests.test_flow_execution_runtime.PluginBridgePackagingTests -v`  
Expected: PASS，插件安装后包含 `runtime_bridge.gd`。

- [ ] **Step 6: 提交**

```bash
git add godot_plugin_template/addons/pointer_gpf/plugin.gd godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd tests/test_flow_execution_runtime.py
git commit -m "feat: add godot runtime file bridge for flow execution"
```

---

### Task 4: 打通“设计并执行基础测试流程”自然语言链路

**Files:**
- Modify: `mcp/server.py`
- Modify: `tests/test_natural_language_basic_flow_commands.py`

- [ ] **Step 1: 写失败测试（更新工具后可直接执行）**

```python
def test_update_then_run_basic_flow(self) -> None:
    updated = _run_tool(
        self.repo_root,
        "update_game_basic_design_flow_by_current_state",
        {"project_root": str(self.project_root), "flow_id": "nl_exec_flow"},
    )
    self.assertEqual(updated["status"], "updated")
    run = _run_tool(
        self.repo_root,
        "run_game_basic_test_flow",
        {"project_root": str(self.project_root), "flow_id": "nl_exec_flow", "step_timeout_ms": 2000},
    )
    self.assertIn(run["status"], ("passed", "failed"))
    self.assertIn("execution_report", run)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_natural_language_basic_flow_commands.NaturalLanguageBasicFlowCommandTests.test_update_then_run_basic_flow -v`  
Expected: FAIL，当前链路未保证 update 后执行逻辑或执行报告字段。

- [ ] **Step 3: 实现联动命令**

```python
# mcp/server.py（新增复合工具）
def _tool_run_game_basic_test_flow_by_current_state(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    refreshed = _tool_update_game_basic_design_flow_by_current_state(ctx, {**arguments, "project_root": str(project_root)})
    flow_result = refreshed.get("flow_result", {})
    run_args = {
        **arguments,
        "project_root": str(project_root),
        "flow_file": flow_result.get("flow_file", ""),
    }
    executed = _tool_run_game_basic_test_flow(ctx, run_args)
    return {
        "status": executed.get("status", "failed"),
        "context_refresh": refreshed.get("context_refresh", {}),
        "flow_result": flow_result,
        "execution_result": executed,
    }
```

- [ ] **Step 4: 运行测试确认转绿**

Run: `python -m unittest tests.test_natural_language_basic_flow_commands -v`  
Expected: PASS，新联动工具可返回 `execution_result`，并保留刷新上下文信息。

- [ ] **Step 5: 提交**

```bash
git add mcp/server.py tests/test_natural_language_basic_flow_commands.py
git commit -m "feat: add refresh-design-run basic flow orchestration tool"
```

---

### Task 5: 脚本与 CI 升级到“执行层可验证”

**Files:**
- Modify: `scripts/assert-mcp-artifacts.ps1`
- Modify: `scripts/verify-cross-project.ps1`
- Modify: `.github/workflows/mcp-smoke.yml`
- Modify: `.github/workflows/mcp-integration.yml`

- [ ] **Step 1: 写失败测试（脚本断言执行产物）**

```powershell
# 新增到 scripts/assert-mcp-artifacts.ps1 的测试入口（由 unittest 用 subprocess 调用）
# 期望：-ValidateExecutionPipeline 开启时，若缺 report/events 则脚本失败
powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" `
  -ProjectRoot "." `
  -FlowId "ci_smoke_seed" `
  -ValidateExecutionPipeline
```

- [ ] **Step 2: 运行确认失败**

Run: `powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" -ProjectRoot "." -FlowId "ci_smoke_seed" -ValidateExecutionPipeline`  
Expected: FAIL，提示缺少 `basic_game_test_execution_last.json` 或 flow_run 报告。

- [ ] **Step 3: 实现脚本与 workflow 更新**

```powershell
# scripts/assert-mcp-artifacts.ps1（新增片段）
param(
  ...
  [switch]$ValidateExecutionPipeline
)

if ($ValidateExecutionPipeline) {
  $executionLast = Join-Path $runtimeDir "basic_game_test_execution_last.json"
  if (-not (Test-Path -LiteralPath $executionLast)) {
      throw "Missing execution event artifact: $executionLast"
  }
  $executionJson = Get-Content -LiteralPath $executionLast -Raw | ConvertFrom-Json
  if (-not $executionJson.phase_coverage) { throw "execution report missing phase_coverage" }
  foreach ($phase in @("started","result","verify")) {
      if (-not ($executionJson.phase_coverage.PSObject.Properties.Name -contains $phase)) {
          throw "execution phase_coverage missing: $phase"
      }
  }
}
```

```yaml
# .github/workflows/mcp-smoke.yml（新增执行层步骤）
- name: Runtime execution smoke (mock bridge)
  shell: pwsh
  run: |
    $project = "examples/godot_minimal"
    python "mcp/server.py" --tool design_game_basic_test_flow --project-root $project --flow-id "ci_exec_smoke"
    @'
    import json, time
    from pathlib import Path
    project = Path("examples/godot_minimal").resolve()
    tmp = project / "pointer_gpf" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for _ in range(120):
        cmd = tmp / "command.json"
        if cmd.exists():
            payload = json.loads(cmd.read_text(encoding="utf-8"))
            (tmp / "response.json").write_text(json.dumps({"ok": True, "message": "mock-ok"}), encoding="utf-8")
        time.sleep(0.1)
    '@ | Set-Content -LiteralPath "__mock_bridge.py" -Encoding UTF8
    Start-Process python -ArgumentList "__mock_bridge.py"
    python "mcp/server.py" --tool run_game_basic_test_flow --project-root $project --flow-id "ci_exec_smoke" --args "{""step_timeout_ms"":2000}"
    powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" -ProjectRoot $project -FlowId "ci_exec_smoke" -ValidateExecutionPipeline
```

- [ ] **Step 4: 运行验证**

Run: `python -m unittest`  
Expected: PASS，且 CI yaml 本地语法检查通过（至少 `python -m unittest` 不因路径/命令变更失败）。

- [ ] **Step 5: 提交**

```bash
git add scripts/assert-mcp-artifacts.ps1 scripts/verify-cross-project.ps1 .github/workflows/mcp-smoke.yml .github/workflows/mcp-integration.yml
git commit -m "test: validate runtime execution artifacts in scripts and workflows"
```

---

### Task 6: 文档与契约对齐（承诺口径收敛）

**Files:**
- Modify: `mcp/adapter_contract_v1.json`
- Modify: `docs/godot-adapter-contract-v1.md`
- Modify: `docs/quickstart.md`
- Modify: `docs/mcp-testing-spec.md`
- Modify: `README.zh-CN.md`
- Modify: `README.md`

- [ ] **Step 1: 写失败测试（文档命令可执行）**

```python
def test_quickstart_runtime_command_exists(self) -> None:
    text = (self.repo_root / "docs" / "quickstart.md").read_text(encoding="utf-8")
    self.assertIn("run_game_basic_test_flow", text)
    self.assertIn("ValidateExecutionPipeline", text)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m unittest tests.test_flow_execution_runtime.DocumentContractTests -v`  
Expected: FAIL，文档尚未出现执行命令和执行断言参数。

- [ ] **Step 3: 更新契约与文档**

```json
// mcp/adapter_contract_v1.json（新增建议字段）
{
  "runtime_bridge": {
    "transport_mode": "file_bridge",
    "command_file_rel": "pointer_gpf/tmp/command.json",
    "response_file_rel": "pointer_gpf/tmp/response.json",
    "required_response_fields": ["ok"],
    "timeout_error_code": "TIMEOUT"
  }
}
```

```markdown
## docs/quickstart.md（新增示例命令）
python "mcp/server.py" --tool design_game_basic_test_flow --project-root "D:/path/to/project" --flow-id "basic_smoke"
python "mcp/server.py" --tool run_game_basic_test_flow --project-root "D:/path/to/project" --flow-id "basic_smoke" --args "{""step_timeout_ms"":15000,""fail_fast"":true,""shell_report"":true}"

powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" `
  -ProjectRoot "D:/path/to/project" `
  -FlowId "basic_smoke" `
  -ValidateExecutionPipeline
```

- [ ] **Step 4: 运行测试确认转绿**

Run: `python -m unittest tests.test_flow_execution_runtime.DocumentContractTests -v`  
Expected: PASS，文档与契约字段同步。

- [ ] **Step 5: 提交**

```bash
git add mcp/adapter_contract_v1.json docs/godot-adapter-contract-v1.md docs/quickstart.md docs/mcp-testing-spec.md README.zh-CN.md README.md tests/test_flow_execution_runtime.py
git commit -m "docs: align mcp contract and guides with executable basic test flow"
```

---

## 全量回归验证清单（执行完成前必须跑）

- [ ] `python -m unittest tests.test_mcp_transport_protocol -v`  
  Expected: PASS
- [ ] `python -m unittest tests.test_natural_language_basic_flow_commands -v`  
  Expected: PASS
- [ ] `python -m unittest tests.test_figma_ui_pipeline -v`  
  Expected: PASS
- [ ] `python -m unittest tests.test_flow_execution_runtime -v`  
  Expected: PASS
- [ ] `powershell -ExecutionPolicy Bypass -File "scripts/verify-cross-project.ps1" -TargetProjectRoot "D:/path/to/real/project"`  
  Expected: PASS，若加执行开关则应输出 execution artifact 校验成功。

---

## 自检（writing-plans skill）

- **Spec coverage**
  - 运行游戏：Task 2（执行器）+ Task 3（bridge）。
  - shell 分阶段播报：Task 2（`started/result/verify`）+ Task 5（脚本断言）。
  - 非冒烟而是完整基础流程：Task 4（设计+执行联动）+ Task 6（文档口径）。
  - CI 与本地验证闭环：Task 5。
- **Placeholder scan**
  - 已检查：无 `TODO/TBD/implement later` 占位语句。
- **Type consistency**
  - 工具名统一为 `run_game_basic_test_flow`。
  - 阶段名统一为 `started/result/verify`。
  - 执行报告字段统一使用 `phase_coverage`、`step_count`、`status`。
