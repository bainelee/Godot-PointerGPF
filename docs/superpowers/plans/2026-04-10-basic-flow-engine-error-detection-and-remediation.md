# 基础测试流程：引擎报错无感与被动等待问题 — 根因分析与完整解决方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `run_game_basic_test_flow` 执行期间，当 Godot 运行态出现脚本/引擎报错时，MCP 能**尽快发现**（而非长时间空等 `response.json`），输出**可观测证据**，并可选进入**与 `auto_fix_game_bug` 衔接的修复路径**；同时约束代理侧不得对长时运行采用「后台挂起、零观测」的执行方式。

**Architecture:** 在现有「文件桥 `command.json` ↔ `response.json`」之上，增加**并行观测面**：(1) 插件侧周期性写出**运行态诊断快照**（错误栈、最近 `push_error`、可选解析错误）到约定路径；(2) `FlowRunner` 在等待响应时**轮询**该快照，命中严重等级则**立即失败**并返回独立错误码；(3) MCP 在 `RUNTIME_GATE_FAILED` / `TIMEOUT` / `ENGINE_RUNTIME_STALLED` 等路径附带 `suggested_next_tool` 与摘录；(4) 文档与 Cursor 规则明确：**Godot Tools / DAP / 日志**与 PointerGPF 约定文件的对应关系，便于人工或第二工具写入诊断文件。

**Tech Stack:** Python 3.11+（`mcp/flow_execution.py`、`mcp/server.py`）、Godot 4.x GDScript（`godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd` 及可选新模块）、现有 `auto_fix_game_bug` / `run_bug_fix_loop`、unittest / CI smoke。

---

## 文件结构（计划范围内）

| 文件 | 职责 |
|------|------|
| `mcp/flow_execution.py` | `FlowRunner`：等待步骤响应时并行观测 `runtime_diagnostics.json`（或等价），缩短无效等待；新异常类型可选 |
| `mcp/server.py` | `run_game_basic_test_flow` 错误体扩展：`blocking_point`、`engine_diagnostics_path`、`suggested_actions`；可选参数 `fail_on_engine_errors` |
| `godot_plugin_template/addons/pointer_gpf/runtime_diagnostics.gd`（新建） | 在 play 进程内 `_process` 收集 `Engine.get_singleton("EditorInterface")` 不可用场景下的运行时错误；或订阅 `push_error` 通过 `ProjectSettings`/`OS.alert` 的替代方案 —— **以 Godot 4 可行为准**：用 `SceneTree` + 自定义 `print_line` 钩子或轮询 `Performance` 不可行处改用**日志文件** `user://` 同步到 `res://pointer_gpf/tmp/`（见 Task 2 具体 API） |
| `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd` | 在处理每条 command 前读取诊断快照并附加到 `response` 的 `diagnostics` 字段（轻量） |
| `godot_plugin_template/addons/pointer_gpf/plugin.gd` | 编辑器侧：若有 `EditorDebuggerPlugin` 或错误面板 API 可用，将**最近一条脚本错误**写入 `pointer_gpf/tmp/editor_script_error.json`（仅编辑器态） |
| `mcp/adapter_contract_v1.json` | 文档化新增 tmp 文件名与字段 schema |
| `docs/design/99-tools/14-mcp-core-invariants.md` | 增补：流程执行中「必须观测运行态错误通道」的不变量 |
| `.cursor/rules/gpf-runtime-test-mandatory-play-mode.mdc` | 增补：禁止将 `run_game_basic_test_flow` 无输出地转入后台；超时必须附带已读取的诊断路径 |
| `tests/test_flow_execution_runtime.py` / 新建 `tests/test_flow_engine_diagnostics.py` | 单测：模拟诊断文件出现后 `FlowRunner` 在 step 超时前失败 |

---

## 根因分析（为何「游戏报错但 MCP 只会等」）

### R1 — 执行模型单一：只认 `response.json`

`FlowRunner._wait_for_response` 在 `deadline` 到达前**仅**检查 `pointer_gpf/tmp/response.json` 的 `seq`/`run_id` 是否匹配（见 `mcp/flow_execution.py` 约 148–174 行）。**没有任何**对以下信号的并行等待：

- Godot 游戏进程崩溃或卡死在未执行桥接逻辑的路径上；
- 脚本运行时错误导致 `_dispatch_action` 未执行到 `_write_response`；
- 编辑器报「解析错误」但 `runtime_gate.json` 仍可能被标为已通过（两路信息不同步）。

**结果：** 表现为 MCP 侧长时间阻塞，用户感知为「在等」，而不是「已发现引擎报错」。

### R2 — 插件桥未要求「错误回传」为协议一等公民

`runtime_bridge.gd` 在 `click`/`check` 等失败时会通过 `_error_payload` 写回 `ok: false`，但若错误发生在**桥接轮询之外**（例如 autoload 先于桥接初始化崩溃、或错误仅在编辑器「错误」面板），则 **MCP 仍收不到响应**。

### R3 — `auto_fix_game_bug` 与 `run_game_basic_test_flow` 未编排

`auto_fix_game_bug` 需要显式 `issue` 字符串（`mcp/server.py` 约 2761–2765 行）。**基础流程运行工具不会**在超时/失败时自动组装 `issue` 或调用修复循环，代理也容易忘记衔接。

### R4 — 代理执行策略失误（会话层）

将 `run_game_basic_test_flow` 通过子进程启动并**转入后台**且不设日志跟随时，即使用户界面已报错，代理也**看不到** stderr 之外的引擎侧信息，加剧「干等」印象。此条需在 Cursor 规则中**显式禁止**或要求「同步等待 + 诊断路径回传」。

### R5 — 与「Godot Tools」未建立数据契约

用户提到可通过 **Godot Tools** 观察报错。当前 PointerGPF **没有**约定路径让编辑器/LSP/DAP 将诊断**写入** `pointer_gpf/tmp/*.json` 供 MCP 轮询，因此两套工具链**并行但不联通**。

---

## Task 1: 契约与 tmp 诊断文件 schema

**Files:**

- Modify: `mcp/adapter_contract_v1.json`（增加 `runtime_diagnostics` 或 `engine_diagnostics` 小节）
- Create: `docs/design/99-tools/16-pointer-gpf-runtime-diagnostics-bridge.md`（简短规范：文件名、字段、刷新频率）

**约定（实现时以此为准）：**

- 路径：`pointer_gpf/tmp/runtime_diagnostics.json`（与 `runtime_gate.json` 同目录）
- 最小字段：

```json
{
  "schema": "pointer_gpf.runtime_diagnostics.v1",
  "updated_at": "2026-04-10T12:00:00Z",
  "source": "game_runtime|editor",
  "severity": "info|warning|error|fatal",
  "summary": "短句，给人读",
  "items": [
    {
      "kind": "script_error|parse_error|engine_error|push_error",
      "message": "…",
      "file": "res://…",
      "line": 12,
      "stack": "可选"
    }
  ]
}
```

- [ ] **Step 1:** 在 `adapter_contract_v1.json` 增加上述 schema 引用与错误码 `ENGINE_DIAGNOSTICS_FATAL`（或并入现有 `STEP_FAILED` 的 `details`）。

- [ ] **Step 2:** 新增设计文档 `16-pointer-gpf-runtime-diagnostics-bridge.md`，说明 MCP 轮询频率建议（≤250ms）与插件写入原子性（先写 `.tmp` 再 rename）。

- [ ] **Step 3:** Commit：`docs: runtime diagnostics bridge contract`

---

## Task 2: Godot 插件 — 运行态与编辑器态诊断写入

**Files:**

- Create: `godot_plugin_template/addons/pointer_gpf/runtime_diagnostics_writer.gd`
- Modify: `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd`（`_process` 开头调用 writer 或在 `_poll_bridge` 前 flush）
- Modify: `godot_plugin_template/addons/pointer_gpf/plugin.gd`（编辑器信号，若可用）

**实现要点（GDScript，需按 Godot 4.2+ 实测 API 微调）：**

- 运行态（游戏 play）：在 `runtime_bridge` 所在 autoload 的 `_process` 中：
  - 使用 `Engine.get_frames_drawn()` 或时间戳节流，每 0.2s 写一次文件，避免每帧写盘。
  - 捕获最近错误：实现 `_log_error_callback` —— Godot 4 可使用 `ProjectSettings` 无法直接钩 `push_error` 时，采用 **在 `runtime_bridge` 内对关键 `_dispatch_action` 用 `try/except` 风格** 不适用于 GDScript；**改用** `OS.get_stdout/stderr` 不可用。务实方案：
    - **方案 A（推荐首版）：** 在 `_dispatch_action` 各分支用 `push_error` 包装并同时 `append` 到内存环形缓冲，再序列化到 `runtime_diagnostics.json`。
    - **方案 B：** 使用 `SceneTree.node_added` 监听并检测 `Node` 名 `Failed` 不适用。以方案 A 为主。
  - 对 **未捕获脚本错误**：启用 `SceneTree.set_auto_accept_quit` 无关；使用 `process_mode` + 子节点 `assert` 仍可能绕过。首版文档声明：**仅保证桥接路径内错误与 `push_error` 汇总**；全量需编辑器通道（Task 2b）。

- 编辑器态（`plugin.gd`）：若存在 `EditorInterface.get_editor_settings()` 与错误列表 API，将**最近一条**解析/编译错误写入 `pointer_gpf/tmp/editor_script_error.json`（同 schema 子集）。若 API 不稳定，**首版可跳过**，在计划中标注 `optional`。

- [ ] **Step 1:** 新建 `runtime_diagnostics_writer.gd`，实现 `flush_to_disk(items: Array, severity: String)`，使用 `FileAccess` 写入 `user://` 再复制到 `res://pointer_gpf/tmp/` —— **注意**：`res://` 在导出/只读环境不可写；示例工程可写时写入 `ProjectSettings.globalize_path("res://pointer_gpf/tmp/runtime_diagnostics.json")`，与现有 bridge 一致。

- [ ] **Step 2:** 在 `runtime_bridge.gd` 的 `_dispatch_action` 每个 `return` 前调用 `writer.note_result(ok, message)`。

- [ ] **Step 3:** 在示例工程 `examples/godot_minimal` 手动验证：故意 `push_error("test")` 后文件出现 `error` 级别条目。

- [ ] **Step 4:** Commit：`feat(plugin): write runtime_diagnostics.json during bridge`

---

## Task 3: FlowRunner 并行观测与快速失败

**Files:**

- Modify: `mcp/flow_execution.py`

- [ ] **Step 1: 写失败单测**（`tests/test_flow_engine_diagnostics.py`）

```python
import json
import threading
import time
import unittest
from pathlib import Path

# 伪代码骨架：在临时 project_root 下创建 bridge 目录，
# 启动线程在 50ms 后写入 runtime_diagnostics.json severity=fatal，
# 启动 FlowRunner 单步 click，不写 response.json，
# 期望在 step_timeout 内抛出 FlowExecutionEngineStalled（新异常）或带 code 的包装。

class TestFlowRunnerObservesDiagnostics(unittest.TestCase):
    def test_fatal_diagnostics_abort_before_bridge_timeout(self) -> None:
        self.fail("implement: new exception + FlowRunner loop")
```

- [ ] **Step 2: 运行测试确认 RED**

```text
python -m unittest tests.test_flow_engine_diagnostics.TestFlowRunnerObservesDiagnostics.test_fatal_diagnostics_abort_before_bridge_timeout -v
# Expected: FAIL (exception class not defined / behavior missing)
```

- [ ] **Step 3: 实现 `FlowExecutionEngineStalled`**

在 `flow_execution.py`：

```python
class FlowExecutionEngineStalled(FlowExecutionTimeout):
    """Bridge silent but engine diagnostics report fatal/error."""
```

- [ ] **Step 4: 在 `_wait_for_response` 循环内加入诊断轮询**

```python
def _read_fatal_diagnostics(self) -> dict | None:
    p = self.options.project_root / "pointer_gpf" / "tmp" / "runtime_diagnostics.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    sev = str(data.get("severity", "")).lower()
    if sev in ("fatal", "error"):
        return data
    return None
```

在 `while time.monotonic() < deadline:` 内每次 `sleep` 前调用；若返回非空则 `raise FlowExecutionEngineStalled(...)` 并设置 `exc.report` 预填 `diagnostics`。

- [ ] **Step 5: `server.py` 捕获新异常**，映射为 `AppError` code `ENGINE_RUNTIME_STALLED`，`details` 含 `diagnostics` 全文与 `suggested_next_tool: auto_fix_game_bug` 及 `issue_template`。

- [ ] **Step 6: 运行测试 GREEN**

```text
python -m unittest tests.test_flow_engine_diagnostics -v
```

- [ ] **Step 7: Commit：** `fix(flow): fail fast on runtime_diagnostics fatal while waiting bridge`

---

## Task 4: MCP 编排 — 失败时自动生成 `issue` 草稿

**Files:**

- Modify: `mcp/server.py`（`_tool_run_game_basic_test_flow` 的 `except` 块与成功路径无关）

- [ ] **Step 1:** 定义函数 `_diagnostics_to_issue_text(d: dict) -> str`：拼接 `summary` 与首条 `items[].message` 与 `file:line`。

- [ ] **Step 2:** 在 `TIMEOUT`、`ENGINE_RUNTIME_STALLED`、`STEP_FAILED` 返回的 JSON（CLI `ok:false` 的 `details`）中加入：

```json
{
  "suggested_next_tool": "auto_fix_game_bug",
  "auto_fix_arguments_suggestion": {
    "issue": "<generated>",
    "max_cycles": 3
  }
}
```

- [ ] **Step 3:** 文档 `docs/mcp-real-runtime-input-contract-design.md` 增加一小节「失败时建议的自动修复入口」。

- [ ] **Step 4:** Commit：`feat(mcp): suggest auto_fix payload on flow failure`

---

## Task 5: 可选参数 `observe_engine_errors` 与 Godot Tools 外挂

**Files:**

- Modify: `mcp/server.py` tool schema for `run_game_basic_test_flow`
- Modify: `docs/mcp-basic-test-flow-reference-usage.md`

- [ ] **Step 1:** 增加布尔参数 `observe_engine_errors`（默认 `true`）。为 `false` 时仅保留旧行为（用于纯桥接回归测试）。

- [ ] **Step 2:** 在参考用法文档中说明：若使用 **Cursor Godot 扩展 / Godot Tools** 能导出诊断 JSON，可写入 `pointer_gpf/tmp/runtime_diagnostics.json` 同 schema，MCP **无需区分来源**，`source` 字段填 `external_godot_tools`。

- [ ] **Step 3:** Commit：`docs: document external diagnostics injection`

---

## Task 6: Cursor 规则与代理行为

**Files:**

- Modify: `.cursor/rules/gpf-runtime-test-mandatory-play-mode.mdc`

- [ ] **Step 1:** 增加条文：**禁止**在用户对「跑基础测试流程」的诉求下，将 `run_game_basic_test_flow` CLI **无跟踪地转入后台**；必须同步等待至退出或超时，并读取 `pointer_gpf/tmp/runtime_diagnostics.json`（若存在）写入用户可见报告。

- [ ] **Step 2:** Commit：`chore(rules): forbid silent background basic flow runs`

---

## Task 7: CI 与回归

- [ ] **Step 1:** 扩展 `tests/test_flow_execution_runtime.py`：mock 诊断文件 + 短超时，断言新错误码路径。

- [ ] **Step 2:** `mcp-smoke` 无需改，除非新增工具名；确认 `python -m unittest tests.test_flow_engine_diagnostics tests.test_flow_execution_runtime` 通过。

- [ ] **Step 3:** Commit：`test: engine diagnostics fast-fail coverage`

---

## Self-Review

**1. Spec coverage**

| 诉求 | Task |
|------|------|
| 立即发现报错 | Task 3 轮询 + Task 2 写入 |
| 观测 | Task 1 schema + Task 2 插件 + Task 5 外部注入 |
| 修复衔接 | Task 4 `auto_fix` 建议参数 |
| 代理「等待」问题 | Task 6 规则 + Task 4 明确失败载荷 |
| Godot Tools | Task 5 外挂文件同 schema |

**2. Placeholder scan：** 无 `TBD`；Task 2 中「方案 B 可选」已标明首版边界。

**3. Type consistency：** 新异常继承 `FlowExecutionTimeout` 便于 `server.py` 统一捕获扩展；`AppError` code 新增需与 `adapter_contract_v1.json` 的 `error_codes` 对齐。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-10-basic-flow-engine-error-detection-and-remediation.md`. Two execution options:**

**1. Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间审查，迭代快  

**2. Inline Execution** — 在本会话用 executing-plans 按 Task 批量执行并设检查点  

**Which approach?**
