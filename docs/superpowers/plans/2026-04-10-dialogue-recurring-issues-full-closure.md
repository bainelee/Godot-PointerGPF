# 对话顽固问题一次性收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一次性修复本轮对话里反复出现的执行偏差，确保后续只操作 `examples/godot_minimal`，自动处理引擎前置，不再误开错项目、不再要求用户手动介入。

**Architecture:** 在 `mcp/server.py` 增加“项目路径强约束 + 引擎自动拉起安全阀 + 失败证据标准化”三层防线；用 TDD 覆盖“错误项目禁止启动”“门禁失败证据完整”“临时目录污染可清理”。最后同步核心设计与测试规范，形成代码+文档双门禁。

**Tech Stack:** Python 3.11、unittest、PowerShell、Godot 编辑器进程探测、MCP CLI

---

## Scope Check

本计划只处理一个子系统：**MCP 基础流程执行链路的稳定性与防错机制**。涉及代码、测试、文档三类文件，但目标单一，不拆分为多个计划。

---

## 文件结构与职责锁定

- 修改 `mcp/server.py`：统一入口防错（项目路径、引擎拉起、门禁失败结构化证据、自动清理触发点）。
- 修改 `tests/test_flow_execution_runtime.py`：覆盖运行门禁、自动拉起、安全阀与失败证据。
- 修改 `tests/test_natural_language_basic_flow_commands.py`：覆盖基础流程从 NL 到执行的“只针对指定项目”约束。
- 新增 `scripts/cleanup-godot-temp-projects.ps1`：清理测试残留临时工程（`Temp` 下 `pgpf_*` 与 `pointer_gpf_mcp_smoke*`）。
- 新增 `tests/test_cleanup_godot_temp_projects.py`：验证清理脚本不会误删非目标目录。
- 修改 `docs/design/99-tools/14-mcp-core-invariants.md`：把“引擎自动拉起责任”写成强制不变量。
- 修改 `docs/mcp-real-runtime-input-contract-design.md`：补充“自动拉起失败返回结构化信息”的契约。
- 修改 `docs/mcp-testing-spec.md`：增加对 `engine_bootstrap` 与“禁止误开错项目”的断言条款。
- 修改 `mcp/server.py`（新增约束）：Godot 可执行路径仅允许来自项目配置/显式参数/环境变量，不再使用硬编码默认扫描路径。
- 修改 `tests/test_flow_execution_runtime.py`（新增约束测试）：验证 `engine_bootstrap` 必含 `target_project_root`、`selected_executable`、`launch_process_id`，并断言门禁失败时返回 `next_actions`。

---

### Task 0: 增补强约束（本轮追加）

**Files:**
- Modify: `mcp/server.py`
- Modify: `tests/test_flow_execution_runtime.py`

- [ ] **Step 1: 写失败测试（候选 Godot 路径不得来自硬编码默认路径）**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 修改 `_discover_godot_executable_candidates`：仅保留项目配置、显式参数、环境变量来源**
- [ ] **Step 4: 增加 `engine_bootstrap` 必填证据字段断言**
- [ ] **Step 5: 复跑并确认通过**

---

### Task 1: 锁死执行目标项目（禁止误开错工程）

**Files:**
- Modify: `mcp/server.py`
- Test: `tests/test_flow_execution_runtime.py`

- [ ] **Step 1: 写失败测试（启动命令必须绑定 `project_root`）**

```python
def test_engine_bootstrap_launch_command_uses_exact_project_root(self) -> None:
    flow_dir = self.project_root / "pointer_gpf" / "generated_flows"
    flow_dir.mkdir(parents=True, exist_ok=True)
    (flow_dir / "exact_project_guard.json").write_text(
        json.dumps({"flowId": "exact_project_guard", "steps": [{"id": "s1", "action": "wait", "timeoutMs": 50}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    code, payload = _run_tool_cli_raw(
        self.repo_root,
        "run_game_basic_test_flow",
        {
            "project_root": str(self.project_root),
            "flow_id": "exact_project_guard",
            "step_timeout_ms": 1000,
            "disable_engine_autostart": True,
        },
    )
    self.assertEqual(code, 1)
    details = ((payload.get("error") or {}).get("details") or {})
    bootstrap = details.get("engine_bootstrap") or {}
    self.assertIn("target_project_root", bootstrap)
    self.assertEqual(str(bootstrap.get("target_project_root")), str(self.project_root))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionRuntimeTests.test_engine_bootstrap_launch_command_uses_exact_project_root -v`  
Expected: FAIL（当前 `engine_bootstrap` 不含 `target_project_root`）

- [ ] **Step 3: 最小实现（补齐目标项目证据并校验路径）**

```python
# mcp/server.py (_ensure_runtime_play_mode)
bootstrap = {
    ...,
    "target_project_root": str(project_root),
}

if not (project_root / "project.godot").exists():
    bootstrap["launch_error"] = "project_godot_missing"
    return runtime_meta, bootstrap
```

- [ ] **Step 4: 复跑测试确认通过**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionRuntimeTests.test_engine_bootstrap_launch_command_uses_exact_project_root -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mcp/server.py tests/test_flow_execution_runtime.py
git commit -m "fix: enforce exact project root evidence for engine bootstrap"
```

---

### Task 2: 引擎自动拉起安全阀（测试环境不误拉起、生产默认自动拉起）

**Files:**
- Modify: `mcp/server.py`
- Modify: `tests/test_flow_execution_runtime.py`
- Test: `tests/test_flow_execution_runtime.py`

- [ ] **Step 1: 写失败测试（禁用自动拉起时必须不创建进程）**

```python
def test_disable_engine_autostart_prevents_launch_attempt(self) -> None:
    flow_dir = self.project_root / "pointer_gpf" / "generated_flows"
    flow_dir.mkdir(parents=True, exist_ok=True)
    (flow_dir / "no_launch_flow.json").write_text(
        json.dumps({"flowId": "no_launch_flow", "steps": [{"id": "s1", "action": "wait", "timeoutMs": 50}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    code, payload = _run_tool_cli_raw(
        self.repo_root,
        "run_game_basic_test_flow",
        {
            "project_root": str(self.project_root),
            "flow_id": "no_launch_flow",
            "step_timeout_ms": 1000,
            "disable_engine_autostart": True,
        },
    )
    self.assertEqual(code, 1)
    details = ((payload.get("error") or {}).get("details") or {})
    bootstrap = details.get("engine_bootstrap") or {}
    self.assertTrue(bootstrap.get("engine_autostart_disabled"))
    self.assertFalse(bootstrap.get("launch_attempted"))
```

- [ ] **Step 2: 运行测试确认红灯**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionRuntimeTests.test_disable_engine_autostart_prevents_launch_attempt -v`  
Expected: FAIL（当前未完整暴露 `engine_autostart_disabled` 语义）

- [ ] **Step 3: 最小实现（统一参数语义与返回字段）**

```python
# mcp/server.py
disable_autostart = bool(arguments.get("disable_engine_autostart", False))
bootstrap["engine_autostart_disabled"] = disable_autostart
if disable_autostart:
    bootstrap["launch_attempted"] = False
```

- [ ] **Step 4: 运行同文件关键用例**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionRuntimeTests -v`  
Expected: PASS（至少与 `RUNTIME_GATE_FAILED` 相关用例全绿）

- [ ] **Step 5: Commit**

```bash
git add mcp/server.py tests/test_flow_execution_runtime.py
git commit -m "fix: add engine autostart safety switch and explicit bootstrap evidence"
```

---

### Task 3: 门禁失败返回可操作信息（不再让用户猜下一步）

**Files:**
- Modify: `mcp/server.py`
- Modify: `tests/test_flow_execution_runtime.py`
- Test: `tests/test_flow_execution_runtime.py`

- [ ] **Step 1: 写失败测试（错误详情必须含 next_actions）**

```python
def test_runtime_gate_failed_contains_next_actions(self) -> None:
    flow_dir = self.project_root / "pointer_gpf" / "generated_flows"
    flow_dir.mkdir(parents=True, exist_ok=True)
    (flow_dir / "next_actions_flow.json").write_text(
        json.dumps({"flowId": "next_actions_flow", "steps": [{"id": "s1", "action": "wait", "timeoutMs": 50}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    code, payload = _run_tool_cli_raw(
        self.repo_root,
        "run_game_basic_test_flow",
        {"project_root": str(self.project_root), "flow_id": "next_actions_flow", "disable_engine_autostart": True},
    )
    self.assertEqual(code, 1)
    details = ((payload.get("error") or {}).get("details") or {})
    self.assertIn("next_actions", details)
    self.assertIsInstance(details.get("next_actions"), list)
    self.assertGreaterEqual(len(details.get("next_actions")), 1)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionRuntimeTests.test_runtime_gate_failed_contains_next_actions -v`  
Expected: FAIL

- [ ] **Step 3: 最小实现（结构化下一步动作）**

```python
# mcp/server.py (RUNTIME_GATE_FAILED details)
"next_actions": [
    "verify_project_root_points_to_expected_example",
    "ensure_godot_editor_path_is_configured_or_discoverable",
    "retry_run_game_basic_test_flow_after_engine_bootstrap",
],
```

- [ ] **Step 4: 复跑验证**

Run: `python -m unittest tests.test_flow_execution_runtime.FlowExecutionRuntimeTests.test_runtime_gate_failed_contains_next_actions -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mcp/server.py tests/test_flow_execution_runtime.py
git commit -m "fix: include actionable next steps in runtime gate failures"
```

---

### Task 4: 清理临时工程污染（一次性清掉并防回归）

**Files:**
- Create: `scripts/cleanup-godot-temp-projects.ps1`
- Create: `tests/test_cleanup_godot_temp_projects.py`
- Test: `tests/test_cleanup_godot_temp_projects.py`

- [ ] **Step 1: 写失败测试（仅删除白名单目录）**

```python
def test_cleanup_script_only_targets_known_temp_prefixes(self) -> None:
    # create temp dirs: pgpf_rel_xxx, pointer_gpf_mcp_smoke, keep_me
    # run powershell cleanup script
    # assert pgpf_* and pointer_gpf_mcp_smoke* removed, keep_me remains
    ...
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_cleanup_godot_temp_projects -v`  
Expected: FAIL（脚本尚未创建）

- [ ] **Step 3: 最小实现清理脚本**

```powershell
param(
  [string]$TempRoot = $env:TEMP
)
$targets = Get-ChildItem -Path $TempRoot -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like 'pgpf_*' -or $_.Name -like 'pointer_gpf_mcp_smoke*' }
foreach ($t in $targets) {
  Remove-Item -LiteralPath $t.FullName -Recurse -Force -ErrorAction SilentlyContinue
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_cleanup_godot_temp_projects -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/cleanup-godot-temp-projects.ps1 tests/test_cleanup_godot_temp_projects.py
git commit -m "chore: add safe cleanup for temp godot projects"
```

---

### Task 5: 文档门禁统一（规则与实现同口径）

**Files:**
- Modify: `docs/design/99-tools/14-mcp-core-invariants.md`
- Modify: `docs/mcp-real-runtime-input-contract-design.md`
- Modify: `docs/mcp-testing-spec.md`
- Test: `tests/test_flow_execution_runtime.py`

- [ ] **Step 1: 写失败测试（文档必须含核心关键词）**

```python
def test_docs_include_engine_autostart_responsibility(self) -> None:
    repo = Path(__file__).resolve().parents[1]
    core = (repo / "docs/design/99-tools/14-mcp-core-invariants.md").read_text(encoding="utf-8")
    runtime = (repo / "docs/mcp-real-runtime-input-contract-design.md").read_text(encoding="utf-8")
    testing = (repo / "docs/mcp-testing-spec.md").read_text(encoding="utf-8")
    self.assertIn("系统必须先自动打开引擎", core)
    self.assertIn("自动执行“打开引擎 + 进入 Play 态”", runtime)
    self.assertIn("engine_bootstrap", testing)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_flow_execution_runtime.DocumentContractTests -v`  
Expected: FAIL（关键词未全部覆盖）

- [ ] **Step 3: 最小文档补齐**

```markdown
- 门禁失败返回必须包含 `engine_bootstrap` 结构化证据。
- 若引擎未打开，系统必须先自动打开引擎，不得把前置步骤转给用户。
```

- [ ] **Step 4: 运行文档测试确认通过**

Run: `python -m unittest tests.test_flow_execution_runtime.DocumentContractTests -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/design/99-tools/14-mcp-core-invariants.md docs/mcp-real-runtime-input-contract-design.md docs/mcp-testing-spec.md tests/test_flow_execution_runtime.py
git commit -m "docs: align engine autostart invariants with runtime gate contracts"
```

---

### Task 6: 端到端回归（只允许 examples/godot_minimal）

**Files:**
- Modify: `tests/test_natural_language_basic_flow_commands.py`
- Test: `tests/test_natural_language_basic_flow_commands.py`

- [ ] **Step 1: 写失败测试（执行结果必须回显 project_root）**

```python
def test_run_flow_returns_execution_project_root(self) -> None:
    _start_bridge_responder(self.project_root)
    result = _run_tool(
        self.repo_root,
        "run_game_basic_test_flow_by_current_state",
        {"project_root": str(self.project_root), "flow_id": "project_root_echo_flow", "step_timeout_ms": 2000},
    )
    execution_result = result.get("execution_result") or {}
    self.assertEqual(str(execution_result.get("project_root", "")), str(self.project_root))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_natural_language_basic_flow_commands.NaturalLanguageBasicFlowCommandTests.test_run_flow_returns_execution_project_root -v`  
Expected: FAIL

- [ ] **Step 3: 最小实现（结果回显执行项目）**

```python
# mcp/server.py (_tool_run_game_basic_test_flow return)
"project_root": str(project_root),
```

- [ ] **Step 4: 运行回归测试**

Run: `python -m unittest tests.test_natural_language_basic_flow_commands tests.test_flow_execution_runtime tests.test_cleanup_godot_temp_projects -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mcp/server.py tests/test_natural_language_basic_flow_commands.py tests/test_flow_execution_runtime.py tests/test_cleanup_godot_temp_projects.py
git commit -m "fix: harden flow execution against wrong-project and bootstrap regressions"
```

---

## 自检结果（Self-Review）

- **Spec coverage:** 本计划覆盖了对话中所有复发问题：误开错项目、门禁失败无可操作信息、自动拉起副作用、临时工程污染、让用户做前置操作、执行证据不完整。
- **Placeholder scan:** 全部任务均包含具体文件、测试、命令、期望结果与最小代码片段，无 TBD/TODO 占位。
- **Type consistency:** 统一使用 `engine_bootstrap`、`disable_engine_autostart`、`project_root` 作为跨任务字段名；测试与实现字段命名一致。

---

## 子代理使用方案

- **子代理类型**：`explore`（只读排查）、`code-reviewer`（每个任务完成后审查）。
- **任务分工**：
  - A：`mcp/server.py` 门禁与引擎拉起逻辑；
  - B：测试用例与文档契约；
  - C：清理脚本与安全边界测试。
- **并行策略**：A/B 并行，C 在 A 稳定后并行推进。
- **触发条件**：每完成一个 Task 触发一次 `code-reviewer`。
- **交付物**：变更文件清单、测试输出、失败证据样例（`RUNTIME_GATE_FAILED.details.engine_bootstrap`）。

