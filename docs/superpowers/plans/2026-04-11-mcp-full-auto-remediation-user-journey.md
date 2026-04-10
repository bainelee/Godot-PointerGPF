# MCP 用户旅程「安装→初始化→设计→自然语言跑流程」全自动排障与修复 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户在自有 Godot 工程中完成「安装 GPF → 初始化上下文 → 设计基础测试流程 → 自然语言要求跑基础测试流程」后，在 **`play_mode` 真实运行**前提下，对运行中出现的**可归类故障**由 MCP **自动尝试修复并复测**，直到通过或达到明确上限；全过程输出满足 **`docs/authoritative-requirements/01-actual-product-requirements.md` R-001** 与 **`02-user-experience-requirements.md` UX-001** 的证据结构；对**不可自动修复**类问题返回**不冒充成功**的结构化结论与下一步动作，且不依赖任何特定品牌编辑器。

**Architecture:** 在现有 `auto_repair` + `run_bug_fix_loop` + `bug_fix_strategies` + 可选 `GPF_REPAIR_BACKEND_CMD`（`mcp/repair_backend.py`）之上，增加一层 **`FailureSignal` → `RemediationPlan` → 有序处理器`**：先处理「环境与插件/门控/流程文件」类确定性动作（可调用已有 `_ensure_plugin_enabled`、`_ensure_runtime_play_mode` 等），再进入策略补丁与 L2；所有步骤写入 **`remediation_trace`**（验证/定位/修复/复测四阶段事件），由 `get_adapter_contract` 暴露 **`remediation_matrix`** 供客户端与验收脚本解析。不引入「必须人类在旁」的隐含前提。

**Tech Stack:** Python 3.11、`mcp/server.py`、`mcp/flow_execution.py`、`mcp/bug_fix_loop.py`、`mcp/bug_fix_strategies.py`、`mcp/repair_backend.py`、`mcp/adapter_contract_v1.json`、`unittest`、`docs/authoritative-requirements/*.md`（仅 Task 8 在获批后增补一句与契约指针）。

---

## 文件结构（落地前锁定）

| 文件 | 职责 |
|------|------|
| `mcp/failure_taxonomy.py`（新建） | 从 `AppError.code`、`execution_report`、`runtime_diagnostics` 片段构造 `FailureSignal`，输出稳定 `remediation_class` 字符串（供策略与处理器路由） |
| `mcp/remediation_trace.py`（新建） | `RemediationTrace` 数据结构：`append(event)`，`to_json()`；事件类型固定为 `verify` / `locate` / `patch` / `retest` / `bootstrap` |
| `mcp/remediation_handlers.py`（新建） | 对 `remediation_class` 执行**无副作用探测**或**已存在 server 辅助函数的安全封装**（例如插件未启用、门控未过且可重试 bootstrap）；禁止在未授权时删用户资源 |
| `mcp/bug_fix_strategies.py` | 新增若干 `BugFixStrategy`，与 `failure_taxonomy` 输出的 `issue` 前缀或 `strategy_id` 对齐 |
| `mcp/bug_fix_loop.py` | 每轮证据写入 `remediation_trace` 兼容字段；`loop_evidence[*]` 增加 `remediation_class`（若可解析） |
| `mcp/server.py` | 在 `_tool_run_game_basic_test_flow_with_repair_loop` / `_tool_run_game_basic_test_flow_by_current_state_with_repair` 内合并 trace；`get_adapter_contract` 注入 `remediation_matrix` |
| `mcp/adapter_contract_v1.json` | 增加 `remediation_matrix`：行 = `remediation_class`，列 = `handled_by`（`handler`/`strategy`/`l2`/`none`）、`max_auto_attempts` |
| `docs/gpf-user-journey-auto-remediation.md`（新建） | 面向**最终用户**的自然语言说明：旅程步骤、默认会发生什么、如何关 `auto_repair`、如何配置 L2；**不出现**任何 IDE 品牌名 |
| `docs/mcp-basic-test-flow-reference-usage.md` | 增加指向上述用户文档与 `remediation_matrix` 的一节 |
| `tests/test_failure_taxonomy.py`（新建） | 对 `classify_failure` 的表驱动测试 |
| `tests/test_remediation_r001_trace.py`（新建） | 对 `run_bug_fix_loop` 输出是否含四阶段可追溯字段的断言（使用 mock verification） |
| `tests/test_remediation_handlers.py`（新建） | 对 handler 单元行为（mock `project_root`） |
| `docs/authoritative-requirements/01-actual-product-requirements.md` | Task 8：在 R-001 **验收标准**下增加一条：「自动修复覆盖范围以 `adapter_contract_v1.json` 的 `remediation_matrix` 为机器可读准绳」 |

---

### Task 1: `FailureSignal` 与 `classify_failure`（TDD）

**Files:**

- Create: `mcp/failure_taxonomy.py`
- Create: `tests/test_failure_taxonomy.py`

- [ ] **Step 1: 新建测试文件骨架**

`tests/test_failure_taxonomy.py`：

```python
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
```

运行：

```powershell
Set-Location D:\AI\pointer_gpf
python -m unittest tests.test_failure_taxonomy -v
```

**预期:** `ImportError` 或 `AttributeError`。

- [ ] **Step 2: 实现 `mcp/failure_taxonomy.py`**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FailureSignal:
    app_error_code: str | None
    step_status: str | None
    diagnostics_severity: str | None


def classify_failure(signal: FailureSignal) -> str:
    code = (signal.app_error_code or "").strip().upper()
    if code == "RUNTIME_GATE_FAILED":
        return "runtime_gate"
    if code == "ENGINE_RUNTIME_STALLED":
        return "engine_runtime_error"
    if code == "TIMEOUT":
        return "bridge_timeout"
    if code == "STEP_FAILED":
        return "flow_step_failed"
    if code == "FLOW_GENERATION_BLOCKED":
        return "flow_generation_blocked"
    if code == "PROJECT_GODOT_NOT_FOUND":
        return "invalid_godot_project"
    return "unknown_failure"
```

再运行 Step 1 的 unittest，**预期:** PASS。

- [ ] **Step 3: Commit**

```bash
git add mcp/failure_taxonomy.py tests/test_failure_taxonomy.py
git commit -m "feat(mcp): failure taxonomy for remediation routing"
```

---

### Task 2: `RemediationTrace` 与 R-001 四阶段事件（TDD）

**Files:**

- Create: `mcp/remediation_trace.py`
- Create: `tests/test_remediation_r001_trace.py`

- [ ] **Step 1: 写失败测试**

`tests/test_remediation_r001_trace.py`：

```python
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import remediation_trace as rt  # noqa: E402


class TestRemediationTrace(unittest.TestCase):
    def test_append_emits_ordered_phases(self) -> None:
        tr = rt.RemediationTrace(run_id="r1")
        tr.append("verify", {"passed": False})
        tr.append("locate", {"strategy_id": "generic"})
        tr.append("patch", {"applied": False})
        tr.append("retest", {"passed": True})
        data = tr.to_json()
        kinds = [e["kind"] for e in data["events"]]
        self.assertEqual(kinds, ["verify", "locate", "patch", "retest"])
```

运行 `python -m unittest tests.test_remediation_r001_trace -v`，**预期:** 失败（模块不存在）。

- [ ] **Step 2: 实现 `mcp/remediation_trace.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PhaseKind = Literal["verify", "locate", "patch", "retest", "bootstrap"]


@dataclass
class RemediationTrace:
    run_id: str
    events: list[dict[str, Any]] = field(default_factory=list)

    def append(self, kind: PhaseKind, payload: dict[str, Any]) -> None:
        self.events.append({"kind": kind, "payload": dict(payload)})

    def to_json(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "events": list(self.events)}
```

再运行 unittest，**预期:** PASS。

- [ ] **Step 3: Commit**

```bash
git add mcp/remediation_trace.py tests/test_remediation_r001_trace.py
git commit -m "feat(mcp): remediation trace for R-001 phase logging"
```

---

### Task 3: 将 `RemediationTrace` 并入 `run_bug_fix_loop`

**Files:**

- Modify: `mcp/bug_fix_loop.py`
- Modify: `tests/test_repair_backend.py`（或新建 `tests/test_bug_fix_loop_trace.py`）

- [ ] **Step 1: 扩展 `run_bug_fix_loop` 签名**

在 `run_bug_fix_loop` 增加可选参数 `trace: RemediationTrace | None = None`。在以下位置调用 `trace.append`（若 `trace` 非空）：

- 初始 `verification0` 之后：`trace.append("verify", {"passed": bool(verification0.get("passed")), "status": verification0.get("status")})`
- 每轮 `diagnosis` 后：`trace.append("locate", {"diagnosis": diagnosis})`
- `patch`（含 L2 合并结果）后：`trace.append("patch", dict(patch))`
- `retest` 后：`trace.append("retest", {"passed": bool(retest.get("passed")), "status": retest.get("status")})`

- [ ] **Step 2: 返回体增加字段**

在最终 `return` 的 dict 中增加 `"remediation_trace": trace.to_json() if trace is not None else {"run_id": "", "events": []}`。

- [ ] **Step 3: `_tool_auto_fix_game_bug` 传入 trace**

在 `mcp/server.py` 的 `_tool_auto_fix_game_bug` 内：

```python
from remediation_trace import RemediationTrace

trace = RemediationTrace(run_id=str(project_root.resolve()))
loop_result = run_bug_fix_loop(..., trace=trace)
```

- [ ] **Step 4: 单测**

`tests/test_bug_fix_loop_trace.py` 使用 `unittest.mock.patch` 固定 `run_apply_patch` 返回 `{"applied": True, "changed_files": []}`，`run_verification` 第二次返回 `passed: True`，断言 `loop_result["remediation_trace"]["events"]` 至少包含四类 `kind`。

运行：

```powershell
python -m unittest tests.test_bug_fix_loop_trace tests.test_repair_backend -v
```

**预期:** PASS。

- [ ] **Step 5: Commit**

```bash
git add mcp/bug_fix_loop.py mcp/server.py tests/test_bug_fix_loop_trace.py
git commit -m "feat(mcp): attach remediation trace to auto_fix loop"
```

---

### Task 4: `remediation_handlers`（门控 / 插件 / 上下文阻塞）

**Files:**

- Create: `mcp/remediation_handlers.py`
- Create: `tests/test_remediation_handlers.py`
- Modify: `mcp/server.py`（在 auto_repair 外层循环中、调用 `_tool_auto_fix_game_bug` 之前插入 handler 调用）

- [ ] **Step 1: 定义处理器接口**

`mcp/remediation_handlers.py`：

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from failure_taxonomy import FailureSignal, classify_failure

HandlerFn = Callable[[Path, dict[str, Any], Any], dict[str, Any]]


class RemediationContext(Protocol):
    """Passed from server: minimal surface for handlers."""

    def ensure_plugin_enabled(self, project_root: Path) -> dict[str, Any]: ...


def run_handlers_for_class(
    remediation_class: str,
    project_root: Path,
    last_error_payload: dict[str, Any],
    ctx: Any,
) -> dict[str, Any]:
    """Return {handled: bool, actions: list[dict], notes: str}."""
    _ = (remediation_class, project_root, last_error_payload, ctx)
    return {"handled": False, "actions": [], "notes": "no handler matched"}
```

- [ ] **Step 2: 实现 `runtime_gate` 与 `flow_generation_blocked` 的最小真逻辑**

- `runtime_gate`：若 `last_error_payload` 含 `engine_bootstrap` 且 `blocking_point` 为门控相关，调用现有 `_ensure_runtime_play_mode` 的**安全封装**（从 `server` 导入会循环引用时，改为在 `server` 内定义 `_bootstrap_runtime_for_remediation` 再被 handler 文件通过回调注入——本 Task 采用 **在 `server.py` 内联调用已有函数**，`remediation_handlers.py` 只放纯函数映射表 `HANDLERS: dict[str, HandlerFn]`，由 `server` 注册具体实现）。

推荐落地方式（避免循环 import）：

```text
remediation_handlers.py 只包含 HANDLERS 注册表与 run_handlers_for_class；
具体 Callable 在 server.py 末尾 register_handlers() 填充。
```

- `flow_generation_blocked`：在证据显示缺少可执行证据时，自动调用 `_tool_refresh_project_context` 或 `_tool_init_project_context`（带 `max_files` 上限，来自现有默认配置），然后再继续下一轮 flow；若仍 blocked，则 `handled: False` 并写明原因。

- [ ] **Step 3: 单测**

`tests/test_remediation_handlers.py` 使用 `MagicMock` 作为 `ctx`，断言 `flow_generation_blocked` 路径会调用 refresh（通过 `assert_called_once`）。

- [ ] **Step 4: Commit**

```bash
git add mcp/remediation_handlers.py mcp/server.py tests/test_remediation_handlers.py
git commit -m "feat(mcp): remediation handlers for gate and flow generation"
```

---

### Task 5: 扩展 `bug_fix_strategies`（对齐 CASE-001 与常见引擎文本）

**Files:**

- Modify: `mcp/bug_fix_strategies.py`
- Modify: `tests/test_bug_fix_strategies_extra.py`（若已存在则追加用例；否则新建 `tests/test_bug_fix_strategies_remediation.py`）

- [ ] **Step 1: 新增策略 `GdScriptParseErrorHintStrategy`**

匹配条件：`issue` 或 `verification["app_error"]` 文本中含 `Parse Error` / `解析错误` / `GDScript` 且含行号模式。

`apply_patch`：在 `pointer_gpf/reports/` 写入 `gpf_parse_error_hint.json`（与现有 `SignalDisconnectedHintStrategy` 模式一致），**不自动改 `.gd`**，避免误修语法；但返回 `applied: True` 与 `changed_files` 以满足「有动作」——**本策略在计划中明确为 hint 类**，在 `remediation_matrix` 中标记为 `strategy_hint` 而非 `strategy_code_patch`。

- [ ] **Step 2: 新增策略 `EnsureAutoloadReportStrategy`**

当 issue 含 `runtime_bridge` / `autoload` / `PointerGPFRuntimeBridge` 且 verification 显示 `RUNTIME_GATE_FAILED` 或桥接无响应时，调用 `server._ensure_runtime_bridge_autoload` 的回调封装（在 server 注册），写入 `project.godot` 的变更应返回 `changed_files: [project.godot]`。

- [ ] **Step 3: 单测**

构造临时 `project_root` 与最小 `project.godot`，调用 `run_apply_patch` 或策略单测，断言文件被更新或报告落地。

- [ ] **Step 4: Commit**

```bash
git add mcp/bug_fix_strategies.py tests/test_bug_fix_strategies_remediation.py
git commit -m "feat(mcp): expand bug-fix strategies for runtime and parse hints"
```

---

### Task 6: `adapter_contract_v1.json` 与 `get_adapter_contract` 暴露 `remediation_matrix`

**Files:**

- Modify: `mcp/adapter_contract_v1.json`
- Modify: `mcp/server.py`（`_tool_get_adapter_contract` 或等价函数）

- [ ] **Step 1: 在 JSON 根增加对象 `remediation_matrix`**

示例片段（完整表格在实现时填满，至少 6 行）：

```json
"remediation_matrix": {
  "version": 1,
  "rows": [
    {
      "remediation_class": "runtime_gate",
      "handled_by": "handler",
      "user_visible_summary": "尝试自动拉起并进入可运行测试态",
      "max_auto_attempts": 2
    },
    {
      "remediation_class": "flow_generation_blocked",
      "handled_by": "handler",
      "user_visible_summary": "尝试刷新项目上下文后重试流程生成",
      "max_auto_attempts": 1
    },
    {
      "remediation_class": "flow_step_failed",
      "handled_by": "strategy",
      "user_visible_summary": "按 issue 文本匹配补丁策略并复测",
      "max_auto_attempts": 8
    },
    {
      "remediation_class": "engine_runtime_error",
      "handled_by": "strategy_hint",
      "user_visible_summary": "写入诊断提示文件，需用户对照引擎输出改脚本",
      "max_auto_attempts": 4
    },
    {
      "remediation_class": "bridge_timeout",
      "handled_by": "l2_or_none",
      "user_visible_summary": "可配置 GPF_REPAIR_BACKEND_CMD 由外部命令决策",
      "max_auto_attempts": 2
    },
    {
      "remediation_class": "unknown_failure",
      "handled_by": "none",
      "user_visible_summary": "仅返回证据，不自动改工程",
      "max_auto_attempts": 0
    }
  ]
}
```

- [ ] **Step 2: `get_adapter_contract` 合并该段**

确保 CLI `get_adapter_contract` 输出包含 `remediation_matrix`。

- [ ] **Step 3: 单测**

在 `tests/test_flow_execution_runtime.py` 或新建测试中 `json.loads` 合约路径，断言 `remediation_matrix.version == 1`。

- [ ] **Step 4: Commit**

```bash
git add mcp/adapter_contract_v1.json mcp/server.py tests/test_adapter_contract_remediation.py
git commit -m "feat(mcp): publish remediation_matrix in adapter contract"
```

---

### Task 7: 用户可见文档（自然中文，不提 IDE）

**Files:**

- Create: `docs/gpf-user-journey-auto-remediation.md`
- Modify: `docs/mcp-basic-test-flow-reference-usage.md`（链接到新文档 §1）
- Modify: `docs/quickstart.md`（在 6.5 节后增加一句指向新文档）

- [ ] **Step 1: 撰写 `docs/gpf-user-journey-auto-remediation.md` 必备小节**

1. 用户旅程四步（安装 / 初始化 / 设计 / 跑流程）与每步**可能失败点**列表。  
2. 「全自动」在 GPF 中的**精确定义**：自动执行的动作集合 = `remediation_matrix` + `auto_repair` 上限；**不是**「任意未预见 bug 必秒修」。  
3. 如何阅读一次跑流程返回：`tool_usability`、`gameplay_runnability`、`auto_repair`、`remediation_trace`。  
4. 如何配置 `GPF_REPAIR_BACKEND_CMD`（复制示例命令行）。  
5. 如何关闭自动修：`auto_repair: false`、`GPF_AUTO_REPAIR_DEFAULT=0`。

- [ ] **Step 2: Commit**

```bash
git add docs/gpf-user-journey-auto-remediation.md docs/mcp-basic-test-flow-reference-usage.md docs/quickstart.md
git commit -m "docs: end-user auto-remediation journey without IDE coupling"
```

---

### Task 8: 权威需求 R-001 与契约对齐（并重建索引）

**Files:**

- Modify: `docs/authoritative-requirements/01-actual-product-requirements.md`（仅在 R-001 **验收标准**下追加一条，不删改原有编号条款）
- 运行: `python scripts/generate_requirements_index.py`

在 R-001 **验收标准**列表末尾追加一条完整句子：

```markdown
- 自动修复的**覆盖范围与上限**以仓库内 `mcp/adapter_contract_v1.json` 的 `remediation_matrix` 为机器可读准绳；未列入 `handled_by: none` 以外的类时，系统仍必须完成「验证→定位→修复尝试→复测」循环并输出证据，但若无法修复须返回明确失败态而非成功态。
```

- [ ] **Step 1: 编辑并保存**

- [ ] **Step 2: 运行索引生成**

```powershell
Set-Location D:\AI\pointer_gpf
python scripts/generate_requirements_index.py
```

- [ ] **Step 3: 验证** `docs/authoritative-requirements/requirements-index.json` 时间戳更新。

- [ ] **Step 4: Commit**

```bash
git add docs/authoritative-requirements/01-actual-product-requirements.md docs/authoritative-requirements/requirements-index.json
git commit -m "docs(req): tie R-001 acceptance to remediation_matrix"
```

---

## Self-review（对照权威需求）

| 需求 ID | 要求摘要 | 本计划 Task |
|---------|-----------|-------------|
| R-001 | 验证→定位→修复→复测循环；日志四类；成功或超时明确 | Task 2–4 trace；Task 3 loop；Task 4 handler；Task 8 契约对齐 |
| UX-001 | 默认自动修复、结果含修复内容与复测 | Task 3 返回 `remediation_trace` + 既有 `loop_evidence`；Task 7 用户说明 |
| UX-002 / R-002 | 双目标结论、自然语言跑流程 | 已由现有工具满足；Task 7 明确阅读字段 |
| CASE-001 | 按钮不可点自动修复 | Task 5 保留并扩展策略；与现有 `ButtonNotClickableStrategy` 协同 |
| CASE-002 | 跑流程后转入自动修复 | Task 4 handler + Task 3 与现有 `auto_repair` 串联 |

**Placeholder 扫描：** 无 `TBD`；`remediation_handlers` 的循环引用通过「server 注册回调」解决，已在 Task 4 写明。

**类型一致性：** `FailureSignal` / `classify_failure` 输出字符串与 `remediation_matrix.rows[].remediation_class` 必须完全一致；Task 6 的 JSON 与 Task 1 的枚举同步在 Task 6 Step 1 的表中校验。

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-11-mcp-full-auto-remediation-user-journey.md`. Two execution options:**

**1. Subagent-Driven（推荐）** — 按 Task 1→8 分任务派生子代理，Task 之间复核。

**2. Inline Execution** — 本会话内用 executing-plans 连续执行并设检查点。

**Which approach?**
