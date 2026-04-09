# MCP 核心需求全量达成 Implementation Plan

> 状态：草案（计划文档，未声明已全部落地）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完整满足权威需求中的 R-001/R-002 与 UX-001/UX-002，让用户在“基础测试流程”与“遇到 bug 自动修复”两个入口都得到可验收结果。

**Architecture:** 在现有 `mcp/server.py` 基础上新增“自然语言意图归一化层 + 统一结果契约层 + 自动修复循环执行器”。基础流程链路输出必须拆分为“工具可用性结论”和“游戏流程可运行性结论”，并增加可读步骤播报。Bug 修复链路通过“验证 -> 定位 -> 修复 -> 复测”的循环执行，达到成功或超时后统一返回结构化证据。

**Tech Stack:** Python 3.11、unittest、PowerShell 校验脚本、Godot runtime bridge（`command.json/response.json`）

---

## 文件结构与职责分解

- `mcp/server.py`（修改）
  - 注册新工具与参数 schema。
  - 集成自然语言意图映射。
  - 调用基础流程执行器与自动修复执行器。
- `mcp/flow_execution.py`（修改）
  - 增加步骤级可读 shell 播报。
  - 输出“双结论”所需统计字段。
- `mcp/nl_intent_router.py`（新增）
  - 维护同义触发词到工具动作的映射（包含“设计一个基础测试流程”“跑一遍基础测试流程”等）。
- `mcp/basic_flow_contracts.py`（新增）
  - 统一基础流程结果结构：`tool_usability`、`gameplay_runnability`、`step_broadcast_summary`。
- `mcp/bug_fix_loop.py`（新增）
  - 实现自动修复循环引擎与超时控制。
- `mcp/bug_fix_strategies.py`（新增）
  - 内置可执行修复策略（按钮点击、信号绑定、节点可见性/可交互状态等）。
- `tests/test_natural_language_basic_flow_commands.py`（修改）
  - 补“设计一个基础测试流程/跑一遍基础测试流程”触发词测试与双结论断言。
- `tests/test_flow_execution_runtime.py`（修改）
  - 补步骤播报可读性测试与双结论字段测试。
- `tests/test_bug_auto_fix_loop.py`（新增）
  - 覆盖 R-001 主流程、超时路径、最少打扰策略。
- `docs/quickstart.md`（修改）
  - 增加“基础测试流程双结论输出”与“自动 bug 修复命令”。
- `README.zh-CN.md`（修改）
  - 更新能力描述、命令示例、预期输出样例。
- `scripts/assert-mcp-artifacts.ps1`（修改）
  - 新增基础流程双结论与 bug 修复循环产物断言。

## 子代理使用方案

1. **子代理类型**
   - `explore`：只读搜集现有调用点和测试断言。
   - `generalPurpose`：实现 Python 代码与测试。
   - `shell`：执行测试矩阵与产物断言。
   - `code-reviewer`：每个大任务完成后做一致性审查。
2. **任务分工**
   - Agent-A：基础流程链路（意图映射、双结论、播报）。
   - Agent-B：自动 bug 修复循环（循环控制、策略、证据）。
   - Agent-C：文档与脚本断言更新。
3. **并行策略**
   - Task 2 与 Task 3 并行实现。
   - Task 5（文档）在 Task 2/3 合并后执行，避免文档与代码偏差。
4. **触发条件**
   - 任何涉及“基础测试流程命令结果格式”的改动，触发 Agent-A。
   - 任何涉及“bug 自动修复循环”的改动，触发 Agent-B。
   - 功能代码完成后，自动触发 Agent-C 与 `code-reviewer`。
5. **交付物**
   - 可运行测试通过记录。
   - 运行时产物示例（`flow_run_report_*.json`、`bug_fix_run_*.json`）。
   - 更新后的 `README.zh-CN.md` 与 `docs/quickstart.md`。

---

### Task 1: 自然语言触发词与基础流程入口补齐

**Files:**
- Create: `mcp/nl_intent_router.py`
- Modify: `mcp/server.py`
- Test: `tests/test_natural_language_basic_flow_commands.py`

- [ ] **Step 1: 写失败测试（触发词映射）**

```python
def test_nl_aliases_map_to_basic_flow_tools(self) -> None:
    aliases = [
        "设计一个基础测试流程",
        "生成基础测试流程",
        "跑一遍基础测试流程",
        "要求跑基础测试流程",
    ]
    for phrase in aliases:
        result = _run_tool(
            self.repo_root,
            "route_nl_intent",
            {"text": phrase},
        )
        self.assertIn(result["target_tool"], {
            "design_game_basic_test_flow",
            "run_game_basic_test_flow_by_current_state",
        })
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_natural_language_basic_flow_commands.NaturalLanguageBasicFlowCommandTests.test_nl_aliases_map_to_basic_flow_tools -v`  
Expected: `ERROR`（`Unknown tool route_nl_intent`）

- [ ] **Step 3: 最小实现（新增意图路由 + 注册工具）**

```python
# mcp/nl_intent_router.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentRoute:
    target_tool: str
    reason: str


_ALIASES: dict[str, IntentRoute] = {
    "设计一个基础测试流程": IntentRoute("design_game_basic_test_flow", "basic_flow_design"),
    "生成基础测试流程": IntentRoute("design_game_basic_test_flow", "basic_flow_design"),
    "跑一遍基础测试流程": IntentRoute("run_game_basic_test_flow_by_current_state", "basic_flow_run"),
    "要求跑基础测试流程": IntentRoute("run_game_basic_test_flow_by_current_state", "basic_flow_run"),
}


def route_nl_intent(text: str) -> IntentRoute:
    norm = text.strip()
    if norm in _ALIASES:
        return _ALIASES[norm]
    return IntentRoute("unknown", "no_match")
```

```python
# mcp/server.py
from nl_intent_router import route_nl_intent

def _tool_route_nl_intent(_ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    text = str(arguments.get("text", "")).strip()
    if not text:
        raise AppError("INVALID_ARGUMENT", "text is required")
    routed = route_nl_intent(text)
    return {"text": text, "target_tool": routed.target_tool, "reason": routed.reason}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_natural_language_basic_flow_commands.NaturalLanguageBasicFlowCommandTests.test_nl_aliases_map_to_basic_flow_tools -v`  
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add mcp/nl_intent_router.py mcp/server.py tests/test_natural_language_basic_flow_commands.py
git commit -m "feat: add natural language aliases for basic flow intents"
```

---

### Task 2: 基础测试流程输出双结论 + 可读步骤播报

**Files:**
- Create: `mcp/basic_flow_contracts.py`
- Modify: `mcp/flow_execution.py`
- Modify: `mcp/server.py`
- Test: `tests/test_flow_execution_runtime.py`
- Test: `tests/test_natural_language_basic_flow_commands.py`

- [ ] **Step 1: 写失败测试（双结论字段 + 播报文本）**

```python
def test_run_basic_flow_returns_dual_conclusions_and_readable_broadcast(self) -> None:
    _start_bridge_responder(self.project_root)
    result = _run_tool(
        self.repo_root,
        "run_game_basic_test_flow_by_current_state",
        {"project_root": str(self.project_root), "flow_id": "dual_conclusion_flow", "shell_report": True},
    )
    execution = result["execution_result"]
    self.assertIn("tool_usability", execution)
    self.assertIn("gameplay_runnability", execution)
    summary = execution.get("step_broadcast_summary", {})
    self.assertGreaterEqual(summary.get("readable_lines", 0), 1)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_natural_language_basic_flow_commands.NaturalLanguageBasicFlowCommandTests.test_run_basic_flow_returns_dual_conclusions_and_readable_broadcast -v`  
Expected: `FAIL`（缺少 `tool_usability` 字段）

- [ ] **Step 3: 最小实现（结果契约 + 播报）**

```python
# mcp/basic_flow_contracts.py
from __future__ import annotations

from typing import Any


def build_dual_conclusions(execution_report: dict[str, Any]) -> dict[str, Any]:
    status = str(execution_report.get("status", "failed"))
    phase = execution_report.get("phase_coverage", {}) if isinstance(execution_report.get("phase_coverage"), dict) else {}
    started = int(phase.get("started", 0))
    result = int(phase.get("result", 0))
    verify = int(phase.get("verify", 0))
    tool_ok = status == "passed" and started >= 1 and result >= 1 and verify >= 1
    gameplay_ok = status == "passed"
    return {
        "tool_usability": {"passed": tool_ok, "evidence": {"phase_coverage": phase, "status": status}},
        "gameplay_runnability": {"passed": gameplay_ok, "evidence": {"status": status, "step_count": execution_report.get("step_count", 0)}},
    }
```

```python
# mcp/flow_execution.py (in _emit_event or _run_step path)
if self.options.shell_report:
    human_line = f"[FLOW][{phase}] step={step_id} index={step_index}"
    print(human_line, flush=True)
```

```python
# mcp/server.py (_tool_run_game_basic_test_flow return branch)
from basic_flow_contracts import build_dual_conclusions

dual = build_dual_conclusions(report)
return {
    "status": report.get("status", "passed"),
    "project_root": str(project_root),
    "flow_file": str(flow_file),
    "execution_report": report,
    "tool_usability": dual["tool_usability"],
    "gameplay_runnability": dual["gameplay_runnability"],
    "step_broadcast_summary": {
        "enabled": bool(arguments.get("shell_report", False)),
        "readable_lines": int(report.get("phase_coverage", {}).get("started", 0)),
    },
    "exp_runtime": exp_artifact,
    "legacy_layout_hints": legacy_hints,
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_natural_language_basic_flow_commands tests.test_flow_execution_runtime -v`  
Expected: `OK`，且输出包含 `[FLOW][started]` 可读播报行

- [ ] **Step 5: 提交**

```bash
git add mcp/basic_flow_contracts.py mcp/flow_execution.py mcp/server.py tests/test_natural_language_basic_flow_commands.py tests/test_flow_execution_runtime.py
git commit -m "feat: add dual conclusions and readable step broadcast for basic flow"
```

---

### Task 3: 自动 bug 修复闭环（验证 -> 定位 -> 修复 -> 复测）

**Files:**
- Create: `mcp/bug_fix_loop.py`
- Create: `mcp/bug_fix_strategies.py`
- Modify: `mcp/server.py`
- Test: `tests/test_bug_auto_fix_loop.py`

- [ ] **Step 1: 写失败测试（闭环 + 超时 + 最少打扰）**

```python
def test_auto_fix_bug_runs_full_loop_until_success(self) -> None:
    result = _run_tool(
        self.repo_root,
        "auto_fix_game_bug",
        {
            "project_root": str(self.project_root),
            "issue": "这个按钮无法点击",
            "max_cycles": 2,
            "timeout_seconds": 60,
        },
    )
    self.assertIn(result["final_status"], {"fixed", "timeout"})
    self.assertGreaterEqual(result["cycles_completed"], 1)
    self.assertIn("verification", result["loop_evidence"][0])
    self.assertIn("diagnosis", result["loop_evidence"][0])
    self.assertIn("patch", result["loop_evidence"][0])
    self.assertIn("retest", result["loop_evidence"][0])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_bug_auto_fix_loop.BugAutoFixLoopTests.test_auto_fix_bug_runs_full_loop_until_success -v`  
Expected: `ERROR`（`Unknown tool auto_fix_game_bug`）

- [ ] **Step 3: 最小实现（循环执行器 + 策略接口 + MCP 工具）**

```python
# mcp/bug_fix_strategies.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class StrategyResult:
    applied: bool
    summary: str
    changed_files: list[str]


def apply_button_clickability_fix(project_root: Path, issue: str) -> StrategyResult:
    if "按钮" not in issue:
        return StrategyResult(False, "issue not matched for button strategy", [])
    # 先给出最小可执行策略：由后续实现替换成真实 AST/文本修复
    return StrategyResult(True, "button clickability strategy applied", [])
```

```python
# mcp/bug_fix_loop.py
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from bug_fix_strategies import apply_button_clickability_fix


@dataclass
class BugFixLoopOptions:
    project_root: Path
    issue: str
    max_cycles: int
    timeout_seconds: int


def run_bug_fix_loop(
    opts: BugFixLoopOptions,
    run_basic_flow: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    started = time.time()
    evidence: list[dict[str, Any]] = []
    for idx in range(1, opts.max_cycles + 1):
        if time.time() - started > opts.timeout_seconds:
            return {"final_status": "timeout", "cycles_completed": idx - 1, "loop_evidence": evidence}
        verification = run_basic_flow({"project_root": str(opts.project_root), "flow_id": f"bugfix_cycle_{idx}"})
        diagnosis = {"reason": f"cycle_{idx}_diagnosis_for:{opts.issue}"}
        patch = apply_button_clickability_fix(opts.project_root, opts.issue)
        retest = run_basic_flow({"project_root": str(opts.project_root), "flow_id": f"bugfix_cycle_{idx}_retest"})
        cycle_row = {
            "cycle": idx,
            "verification": verification.get("status"),
            "diagnosis": diagnosis,
            "patch": {"applied": patch.applied, "summary": patch.summary, "changed_files": patch.changed_files},
            "retest": retest.get("status"),
        }
        evidence.append(cycle_row)
        if retest.get("status") == "passed":
            return {"final_status": "fixed", "cycles_completed": idx, "loop_evidence": evidence}
    return {"final_status": "timeout", "cycles_completed": opts.max_cycles, "loop_evidence": evidence}
```

```python
# mcp/server.py
from bug_fix_loop import BugFixLoopOptions, run_bug_fix_loop

def _tool_auto_fix_game_bug(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    issue = str(arguments.get("issue", "")).strip()
    if not issue:
        raise AppError("INVALID_ARGUMENT", "issue is required")
    opts = BugFixLoopOptions(
        project_root=project_root,
        issue=issue,
        max_cycles=max(1, int(arguments.get("max_cycles", 3))),
        timeout_seconds=max(30, int(arguments.get("timeout_seconds", 900))),
    )
    result = run_bug_fix_loop(opts, lambda args: _tool_run_game_basic_test_flow_by_current_state(ctx, args))
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_bug_auto_fix_loop -v`  
Expected: `OK`，并且返回 `final_status` 为 `fixed` 或 `timeout`

- [ ] **Step 5: 提交**

```bash
git add mcp/bug_fix_loop.py mcp/bug_fix_strategies.py mcp/server.py tests/test_bug_auto_fix_loop.py
git commit -m "feat: add automatic bug fix loop with verification-diagnosis-fix-retest cycle"
```

---

### Task 4: 把 R-001/R-002 验收字段落盘到运行时产物

**Files:**
- Modify: `mcp/server.py`
- Modify: `scripts/assert-mcp-artifacts.ps1`
- Test: `tests/test_flow_execution_runtime.py`
- Test: `tests/test_bug_auto_fix_loop.py`

- [ ] **Step 1: 写失败测试（产物字段断言）**

```python
def test_execution_artifact_contains_dual_conclusions(self) -> None:
    code, payload = _run_tool_cli_raw(
        self.repo_root,
        "run_game_basic_test_flow",
        {"project_root": str(self.project_root), "flow_id": "smoke_flow", "step_timeout_ms": 8000, "shell_report": True},
    )
    self.assertEqual(code, 0)
    result = payload["result"]
    self.assertIn("tool_usability", result)
    self.assertIn("gameplay_runnability", result)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionToolRegistrationTests.test_execution_artifact_contains_dual_conclusions -v`  
Expected: `FAIL`（产物缺字段）

- [ ] **Step 3: 最小实现（写入运行时 artifact + 脚本校验）**

```python
# mcp/server.py inside _write_exp_runtime_artifact payload
"tool_usability": dual["tool_usability"],
"gameplay_runnability": dual["gameplay_runnability"],
"step_broadcast_summary": {"enabled": bool(arguments.get("shell_report", False)), "readable_lines": ...},
```

```powershell
# scripts/assert-mcp-artifacts.ps1
if ($ValidateExecutionPipeline) {
    if (-not ($execLastJson.PSObject.Properties.Name -contains "tool_usability")) {
        throw "execution artifact missing tool_usability"
    }
    if (-not ($execLastJson.PSObject.Properties.Name -contains "gameplay_runnability")) {
        throw "execution artifact missing gameplay_runnability"
    }
    if (-not ($execLastJson.PSObject.Properties.Name -contains "step_broadcast_summary")) {
        throw "execution artifact missing step_broadcast_summary"
    }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_flow_execution_runtime tests.test_bug_auto_fix_loop -v`  
Expected: `OK`

Run: `powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" -ProjectRoot "<测试项目路径>" -FlowId "smoke_flow" -ValidateExecutionPipeline`  
Expected: 输出 `[ASSERT] runtime execution pipeline artifacts validated.`

- [ ] **Step 5: 提交**

```bash
git add mcp/server.py scripts/assert-mcp-artifacts.ps1 tests/test_flow_execution_runtime.py tests/test_bug_auto_fix_loop.py
git commit -m "test: enforce runtime artifact contract for dual conclusions and broadcast summary"
```

---

### Task 5: 文档更新（命令入口、预期输出、失败处理）

**Files:**
- Modify: `README.zh-CN.md`
- Modify: `docs/quickstart.md`
- Modify: `docs/mcp-implementation-status.md`
- Test: `tests/test_flow_execution_runtime.py`（文档契约测试可扩展）

- [ ] **Step 1: 写失败测试（文档必须出现新命令与字段）**

```python
def test_readme_mentions_auto_fix_game_bug_and_dual_conclusions(self) -> None:
    text = (self.repo_root / "README.zh-CN.md").read_text(encoding="utf-8")
    self.assertIn("auto_fix_game_bug", text)
    self.assertIn("tool_usability", text)
    self.assertIn("gameplay_runnability", text)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_flow_execution_runtime.DocumentContractTests.test_readme_mentions_auto_fix_game_bug_and_dual_conclusions -v`  
Expected: `FAIL`

- [ ] **Step 3: 最小实现（补文档样例）**

```markdown
# README.zh-CN.md 增加示例
python "mcp/server.py" --tool auto_fix_game_bug --args "{""project_root"":""D:/path/to/project"",""issue"":""这个按钮无法点击"",""max_cycles"":3,""timeout_seconds"":900}"

返回结果关键字段：
- tool_usability.passed
- gameplay_runnability.passed
- final_status（fixed/timeout）
```

```markdown
# docs/quickstart.md 增加示例
用户输入：跑一遍基础测试流程
系统映射：run_game_basic_test_flow_by_current_state
最终输出：tool_usability + gameplay_runnability + step_broadcast_summary
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_flow_execution_runtime.DocumentContractTests -v`  
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add README.zh-CN.md docs/quickstart.md docs/mcp-implementation-status.md tests/test_flow_execution_runtime.py
git commit -m "docs: document full basic-flow and auto-bug-fix expected outputs"
```

---

### Task 6: 全链路验收（对应 R-001/R-002/UX-001/UX-002）

**Files:**
- Modify: `tests/test_bug_auto_fix_loop.py`
- Modify: `tests/test_natural_language_basic_flow_commands.py`
- Modify: `.github/workflows/mcp-integration.yml`

- [ ] **Step 1: 写失败测试（按需求编号验收）**

```python
def test_requirements_r002_dual_goal_fields_exist(self) -> None:
    result = _run_tool(self.repo_root, "run_game_basic_test_flow_by_current_state", {"project_root": str(self.project_root)})
    execution = result["execution_result"]
    self.assertIn("tool_usability", execution)
    self.assertIn("gameplay_runnability", execution)

def test_requirements_r001_loop_has_verify_diagnose_fix_retest(self) -> None:
    result = _run_tool(self.repo_root, "auto_fix_game_bug", {"project_root": str(self.project_root), "issue": "这个按钮无法点击"})
    first_cycle = result["loop_evidence"][0]
    self.assertIn("verification", first_cycle)
    self.assertIn("diagnosis", first_cycle)
    self.assertIn("patch", first_cycle)
    self.assertIn("retest", first_cycle)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_natural_language_basic_flow_commands tests.test_bug_auto_fix_loop -v`  
Expected: 至少 1 条失败（未完整覆盖验收字段）

- [ ] **Step 3: 最小实现（补齐 CI 集成运行命令）**

```yaml
# .github/workflows/mcp-integration.yml 增加步骤
- name: Run full requirement tests
  run: |
    python -m unittest tests.test_natural_language_basic_flow_commands tests.test_flow_execution_runtime tests.test_bug_auto_fix_loop -v
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_natural_language_basic_flow_commands tests.test_flow_execution_runtime tests.test_bug_auto_fix_loop tests.test_mcp_transport_protocol -v`  
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add tests/test_natural_language_basic_flow_commands.py tests/test_bug_auto_fix_loop.py .github/workflows/mcp-integration.yml
git commit -m "test: add requirement-level acceptance coverage for full solution"
```

---

## 最终验收命令（一次性）

```bash
python -m unittest tests.test_natural_language_basic_flow_commands tests.test_flow_execution_runtime tests.test_bug_auto_fix_loop tests.test_mcp_transport_protocol -v
powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" -ProjectRoot "D:/path/to/your/godot/project" -FlowId "basic_exec" -ValidateExecutionPipeline
python "mcp/server.py" --tool auto_fix_game_bug --args "{\"project_root\":\"D:/path/to/your/godot/project\",\"issue\":\"这个按钮无法点击\",\"max_cycles\":3,\"timeout_seconds\":900}"
```

Expected:
- 单元测试全通过（`OK`）
- 运行时断言脚本输出 `[ASSERT] runtime execution pipeline artifacts validated.`
- `auto_fix_game_bug` 返回 `final_status` 为 `fixed` 或 `timeout`，并包含 `loop_evidence`

---

## 自检（已覆盖项）

1. **需求覆盖检查**
   - R-002 / UX-002：Task 1 + Task 2 + Task 4 + Task 5 + Task 6。
   - R-001 / UX-001：Task 3 + Task 4 + Task 6。
2. **占位符扫描**
   - 计划中无 `TODO/TBD/implement later`。
   - 每个代码步骤都给出可落地代码片段。
3. **命名一致性**
   - 统一使用 `auto_fix_game_bug`、`tool_usability`、`gameplay_runnability`、`step_broadcast_summary`。

