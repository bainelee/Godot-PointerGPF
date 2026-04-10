# MCP「跑流程」默认完成修复闭环 — 统一实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当用户通过自然语言或工具调用要求「跑一遍基础测试流程」时，MCP 在**默认参数**下完成：**真实 play_mode 执行 → 失败则自动进入修复-复测闭环（有上限）→ 返回结构化结果，其中包含失败原因、每轮修复动作与变更文件**；与根目录 `README.md` 所述产品边界一致，并消除与 `docs/design/99-tools/14-mcp-core-invariants.md` 中「自动修非默认串联」条文的矛盾。

**Architecture:** 在 `mcp/server.py` 中提取单一的 **`_run_basic_flow_with_repair_bundle`**（名称可微调），由 `run_game_basic_test_flow`、`run_game_basic_test_flow_by_current_state` 在默认配置下直接调用；`run_basic_test_flow_orchestrated` 退化为该核心的薄包装或标记弃用后删除，避免两套语义。修复能力分两层：**（L1）** 仓库内 `mcp/bug_fix_strategies.py` 的可验证策略补丁；**（L2）** 可插拔 **Repair Backend**（优先从你提供的旧工程 MCP 中迁移实现：子进程、HTTP 或 stdio 协议之一），在 L1 未应用补丁或复测仍失败时调用，保证「彻底」方案可扩展到任意类错误，而不是仅靠 4 个策略。

**Tech Stack:** Python 3.x、`mcp/server.py`、`mcp/bug_fix_loop.py`、`mcp/bug_fix_strategies.py`、`mcp/nl_intent_router.py`、现有 `unittest` CLI 测试模式、`docs/design/99-tools/14-mcp-core-invariants.md`、环境变量与 `gtr.config.json` 扩展字段。

---

## 文件结构（落地前锁定）

| 文件 | 职责 |
|------|------|
| `mcp/server.py` | 工具入口；调用统一「流程+修复」核心；工具 schema 默认值 |
| `mcp/flow_repair_bundle.py`（新建，推荐） | `run_flow_then_repair_loop`：封装「执行 flow → 失败构造 issue → bug_fix_loop → 汇总 rounds」纯函数，便于单测 |
| `mcp/bug_fix_loop.py` | 保持循环骨架；必要时注入 `RepairBackend` 回调 |
| `mcp/bug_fix_strategies.py` | L1 策略；从旧工程迁移新增策略 |
| `mcp/repair_backend.py`（新建） | `RepairBackend` 协议 + `NullBackend` + `SubprocessJsonBackend`（具体 JSON 契约见下文 Task 4） |
| `mcp/nl_intent_router.py` | 「跑流程」仍路由到 `run_game_basic_test_flow_by_current_state`（行为由默认参数满足预期，无需改 target_tool 除非你想单独暴露 `dry_run` 工具名） |
| `tests/test_flow_execution_runtime.py` | 更新默认行为与 opt-out 断言 |
| `tests/test_bug_auto_fix_loop.py` | 扩展：L2 backend mock |
| `tests/test_nl_intent_router_expanded.py` | 若 NL 表或路由逻辑变更则更新 |
| `docs/design/99-tools/14-mcp-core-invariants.md` | 重写「自动修」条目：默认串联 + opt-out + 上限 |
| `docs/mcp-basic-test-flow-reference-usage.md` | 第 4、7 节与表格：默认带修复；如何关闭 |
| `README.md` / `README.zh-CN.md` | 与不变量一致的一句话 |
| `docs/mcp-real-runtime-input-contract-design.md` | §8 若涉及错误体字段 `repair_summary` 则补充 |

---

### Task 0: 旧工程 MCP 对照清单（必须先做，否则 L2 只能是空壳）

**Files:**

- Create: `docs/superpowers/notes/2026-04-10-legacy-mcp-parity-checklist.md`（本任务输出物）
- Read-only: 你提供的旧仓库路径（环境变量 `GPF_LEGACY_MCP_ROOT`，本地路径，不入库密钥）

- [ ] **Step 1: 建立对照表**

在笔记中列出旧 MCP 中**与「跑流程+自动修」相关的**：

- 工具名列表、参数默认值、失败时是否自动调用修复、最大轮次
- 修复实现位置（单文件路径）、是否调用外部 CLI、环境变量名
- 策略类或规则表（文件路径 + 类名）

- [ ] **Step 2: 用目录对比生成差异草稿**

在仓库根执行（将 `OLD` 换为你的旧工程根目录）：

```powershell
Set-Location D:\AI\pointer_gpf
# 若旧工程在同机：递归列出含 repair / flow / auto_fix 的文件名
Get-ChildItem -Path "OLD" -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match 'mcp|flow|fix|repair|bug' } |
  Select-Object -ExpandProperty FullName
```

把输出粘贴进 `2026-04-10-legacy-mcp-parity-checklist.md` 的「旧侧文件清单」。

- [ ] **Step 3: 标记本仓库缺口**

在同一份笔记增加表格列：`旧行为 | 本仓库当前 | 本计划 Task 编号`，至少覆盖：

- 默认是否串联 `auto_fix`
- 策略数量与匹配条件
- 是否存在 L2 后端

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/notes/2026-04-10-legacy-mcp-parity-checklist.md
git commit -m "docs: legacy MCP parity checklist for run-flow auto-repair"
```

---

### Task 1: 新建 `flow_repair_bundle` 核心（TDD）

**Files:**

- Create: `mcp/flow_repair_bundle.py`
- Create: `tests/test_flow_repair_bundle.py`
- Modify: `mcp/server.py`（仅在 Task 2 接线；本 Task 末尾可先不改动 server）

- [ ] **Step 1: 写失败测试（修复关闭时行为不变）**

`tests/test_flow_repair_bundle.py`（导入方式与 `tests/test_mcp_hard_teardown.py` 一致：`mcp/` 非包，需插入 `sys.path`）：

```python
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import flow_repair_bundle  # noqa: E402


class TestFlowRepairBundle(unittest.TestCase):
    def test_auto_repair_disabled_only_runs_flow_fn(self) -> None:
        calls: list[str] = []

        def fake_flow() -> dict:
            calls.append("flow")
            return {"execution_result": {"status": "failed"}}

        def fake_repair(_issue: str) -> dict:
            calls.append("repair")
            return {}

        out = flow_repair_bundle.run_flow_once_and_maybe_repair(
            project_root=Path("."),
            auto_repair_enabled=False,
            max_repair_rounds=2,
            auto_fix_max_cycles=3,
            run_flow_bundle=fake_flow,
            run_auto_fix_bundle=fake_repair,
            build_issue_from_failure=lambda r: "x",
        )
        self.assertEqual(calls, ["flow"])
        self.assertEqual(out["final_status"], "failed_without_repair")

    def test_auto_repair_enabled_calls_repair_when_failed(self) -> None:
        calls: list[str] = []

        def fake_flow() -> dict:
            calls.append("flow")
            return {"execution_result": {"status": "failed"}}

        def fake_repair(kwargs: dict) -> dict:
            calls.append("repair")
            return {"final_status": "exhausted", "cycles_completed": 1, "loop_evidence": []}

        out = flow_repair_bundle.run_flow_once_and_maybe_repair(
            project_root=Path("."),
            auto_repair_enabled=True,
            max_repair_rounds=1,
            auto_fix_max_cycles=1,
            run_flow_bundle=fake_flow,
            run_auto_fix_bundle=lambda kw: fake_repair(kw),
            build_issue_from_failure=lambda r: "step failed",
        )
        self.assertEqual(calls, ["flow", "repair"])
        self.assertIn("repair_rounds", out)
```

运行：

```powershell
Set-Location D:\AI\pointer_gpf
python -m unittest tests.test_flow_repair_bundle -v
```

**预期:** `ImportError` 或 `AttributeError`（模块/函数不存在）。

- [ ] **Step 2: 实现最小 `run_flow_once_and_maybe_repair`**

`mcp/flow_repair_bundle.py`：

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

RunFlowFn = Callable[[], dict[str, Any]]
AutoFixFn = Callable[[dict[str, Any]], dict[str, Any]]
IssueFn = Callable[[dict[str, Any]], str]


def run_flow_once_and_maybe_repair(
    *,
    project_root: Path,
    auto_repair_enabled: bool,
    max_repair_rounds: int,
    auto_fix_max_cycles: int,
    run_flow_bundle: RunFlowFn,
    run_auto_fix_bundle: AutoFixFn,
    build_issue_from_failure: IssueFn,
    extra_auto_fix_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bundle = run_flow_bundle()
    er = bundle.get("execution_result") if isinstance(bundle.get("execution_result"), dict) else {}
    if str(er.get("status", "")).strip() == "passed":
        return {"final_status": "passed", "flow_bundle": bundle, "repair_rounds": []}

    if not auto_repair_enabled:
        return {
            "final_status": "failed_without_repair",
            "flow_bundle": bundle,
            "repair_rounds": [],
        }

    issue = build_issue_from_failure(bundle)
    base = {"project_root": str(project_root.resolve()), "issue": issue, "max_cycles": auto_fix_max_cycles}
    if extra_auto_fix_args:
        base.update(extra_auto_fix_args)
    repair_payload = run_auto_fix_bundle(base)
    return {
        "final_status": "repaired_attempted",
        "flow_bundle": bundle,
        "repair_rounds": [{"round_index": 1, "auto_fix": repair_payload}],
    }
```

**注意：** 以上为 Task 1 最小通过版本；Task 2 将扩展为**多轮**（与当前 `run_basic_test_flow_orchestrated` 逻辑等价），可把多轮循环从 `server.py` 移入本模块的 `run_multi_round_flow_repair`。

再运行 Step 1 的 unittest，**预期:** PASS。

- [ ] **Step 3: Commit**

```bash
git add mcp/flow_repair_bundle.py tests/test_flow_repair_bundle.py
git commit -m "feat(mcp): flow_repair_bundle skeleton for unified run+repair"
```

---

### Task 2: 将默认「跑流程」接入修复闭环（修改 `server.py`）

**Files:**

- Modify: `mcp/server.py`（`_tool_run_game_basic_test_flow`、`_tool_run_game_basic_test_flow_by_current_state`、`_build_tool_specs` 中对应 JSON schema）
- Modify: `tests/test_flow_execution_runtime.py`（增加 `auto_repair=false` 以固定原 smoke 行为）
- Modify: `tests/test_mcp_hard_teardown.py`（若集成路径变化）

- [ ] **Step 1: 定义统一参数（默认值与旧行为对照）**

在 `mcp/server.py` 顶部或工具参数解析处增加常量（示例）：

```python
_DEFAULT_AUTO_REPAIR = True
_DEFAULT_MAX_REPAIR_ROUNDS = 2
_DEFAULT_AUTO_FIX_MAX_CYCLES = 3
```

新增工具参数（两个 run 工具均支持）：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `auto_repair` | bool | `True` | `False` 时等价于当前「只跑流程」 |
| `max_repair_rounds` | int | `2` | 范围 1–8，与现编排一致 |
| `auto_fix_max_cycles` | int | `3` | 每轮传入 `auto_fix_game_bug` |

环境变量覆盖（CI 友好）：

```python
import os

def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip() not in ("0", "false", "False", "")
```

- `GPF_AUTO_REPAIR_DEFAULT`：`0` 时全局默认 `auto_repair=False`（不改变显式 JSON `true`）。

- [ ] **Step 2: 把 `_tool_run_basic_test_flow_orchestrated` 的循环迁入 `flow_repair_bundle.run_multi_round_flow_repair`**

逻辑要求：

1. 每轮调用 `_tool_run_game_basic_test_flow_by_current_state` 或内部等价「只执行 runner、不重复 bootstrap」函数，**避免**重复复制粘贴 80 行。
2. `AppError` 路径与 `execution_result.status != passed` 路径均构造 `issue`（复用 `_issue_text_from_flow_app_error` / `_issue_text_from_execution_payload`）。
3. 若 `auto_fix_max_cycles == 0`，跳过 `auto_fix` 但记录 `skipped`。
4. 任意轮 `passed` → 立即返回 `final_status: passed`。

- [ ] **Step 3: `_tool_run_game_basic_test_flow` 在 flow 跑完后**

当前结构：`runner.run` 直接产出 report。成功路径保持不变；**失败路径**在 `auto_repair=True` 时不应立即 `raise` 到客户端，而是：

- 先 `closeProject`（已有 `_maybe_request_project_close` 逻辑保持）
- 进入 `run_multi_round_flow_repair`，其中首轮的「flow」应使用**同一次** flow 失败结果作为 issue 来源，避免无意义重跑两次

若现有代码结构在失败时只 `raise AppError`，需要重构为：**先构建 `execution_result` 字典**，再交给 `flow_repair_bundle` 决定是否 `raise` 或返回 `200` 且 `result.final_status=exhausted_rounds`。

- [ ] **Step 4: 更新测试 —— 显式关闭 auto_repair**

所有**仅验证「单次执行、不报修复」**的测试，在 `--args` JSON 中加：

```json
"auto_repair": false
```

例如 `test_cli_run_game_basic_test_flow_with_flow_id_succeeds` 保持不变成功路径；失败路径测试加 `auto_repair: false` 以免引入 flaky 策略写盘。

新建测试 `test_run_game_basic_test_flow_auto_repair_default_invokes_auto_fix_on_failure`：使用 `unittest.mock.patch` 将 `_tool_auto_fix_game_bug` 替换为记录调用的 stub，构造必然失败的 flow fixture（可用临时 `project_root` + 最小非法 flow），断言 stub 被调用至少一次。

运行：

```powershell
python -m unittest tests.test_flow_execution_runtime tests.test_flow_repair_bundle -v
```

**预期:** 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add mcp/server.py mcp/flow_repair_bundle.py tests/test_flow_execution_runtime.py
git commit -m "feat(mcp): default auto_repair on basic test flow tools"
```

---

### Task 3: 编排工具去重与兼容

**Files:**

- Modify: `mcp/server.py`
- Modify: `tests/test_flow_execution_runtime.py`（`test_run_basic_test_flow_orchestrated_requires_explicit_opt_in`）

- [ ] **Step 1: 将 `run_basic_test_flow_orchestrated` 改为兼容别名**

实现二选一（在计划中固定选 A 或 B，推荐 A）：

- **A（推荐）:** `run_basic_test_flow_orchestrated` 保留，但 **`orchestration_explicit_opt_in` 默认视为已满足**当且仅当调用方仍传 `true`；同时文档标明「与 `run_game_basic_test_flow_by_current_state` + 默认 `auto_repair` 等价」，**6 个月后删除**该工具。
- **B:** 删除 `run_basic_test_flow_orchestrated`，所有引用改指向默认 run 工具；测试删除 opt-in 用例，改为测试 `auto_repair` 默认开启。

- [ ] **Step 2: 更新 CLI 测试**

若选 A：将 `test_run_basic_test_flow_orchestrated_requires_explicit_opt_in` 改为「未传 opt-in 时行为与 `auto_repair=true` 一致」或「仍要求 opt-in 但 run 工具已默认修复」——**二者只留一种产品语义**；推荐 **删除** 对 `orchestration_explicit_opt_in=false` 的 `INVALID_ARGUMENT` 断言，改为断言 orchestration 工具与 by_current_state 返回结构字段一致（`repair_rounds` 存在性）。

- [ ] **Step 3: Commit**

```bash
git add mcp/server.py tests/test_flow_execution_runtime.py
git commit -m "refactor(mcp): deprecate redundant orchestration tool surface"
```

---

### Task 4: L2 Repair Backend（彻底方案的可扩展部分）

**Files:**

- Create: `mcp/repair_backend.py`
- Modify: `mcp/bug_fix_loop.py`
- Create: `tests/test_repair_backend.py`

- [ ] **Step 1: 定义协议**

`mcp/repair_backend.py`：

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class RepairContext:
    project_root: Path
    issue: str
    verification: dict[str, Any]
    diagnosis: dict[str, Any]


class RepairBackend(Protocol):
    def try_patch(self, ctx: RepairContext) -> dict[str, Any]:
        """返回 {applied: bool, changed_files: list[str], notes: str, backend_id: str}"""


class NullBackend:
    backend_id = "null"

    def try_patch(self, ctx: RepairContext) -> dict[str, Any]:
        return {"applied": False, "changed_files": [], "notes": "null backend", "backend_id": self.backend_id}
```

- [ ] **Step 2: 在 `run_bug_fix_loop` 中插入钩子**

在 `run_apply_patch` **之后**、**retest 之前**增加：

```python
# 伪代码位置：mcp/bug_fix_loop.py 内层循环
patch_result = run_apply_patch(project_root, issue, diagnosis)
if not patch_result.get("applied") and repair_backend is not None:
    patch_result = repair_backend.try_patch(
        RepairContext(project_root=project_root, issue=issue, verification=verification, diagnosis=diagnosis)
    )
```

`run_bug_fix_loop` 签名增加可选参数 `repair_backend: RepairBackend | None = None`。

- [ ] **Step 3: `SubprocessJsonBackend`（最小可用）**

从环境变量 `GPF_REPAIR_BACKEND_CMD` 读取命令模板，例如：

`codex exec --json --issue {issue_file} --project {project_root}`

由 Python 写入临时 `issue.json`（含 `issue`、`verification`、`diagnosis`），子进程 stdout 必须为一行 JSON：

```json
{"applied": true, "changed_files": ["res://foo.gd"], "notes": "..."}
```

若解析失败 → `applied: false`。

- [ ] **Step 4: 单测**

`tests/test_repair_backend.py` 使用假脚本 `python -c "print(...)"` 验证解析路径。

- [ ] **Step 5: Commit**

```bash
git add mcp/repair_backend.py mcp/bug_fix_loop.py tests/test_repair_backend.py
git commit -m "feat(mcp): pluggable L2 repair backend hook"
```

---

### Task 5: 从旧工程迁移策略与后端默认命令

**Files:**

- Modify: `mcp/bug_fix_strategies.py`
- Modify: `install/start-mcp.ps1` 或 `docs/quickstart.md`（示例 `GPF_REPAIR_BACKEND_CMD`）

- [ ] **Step 1:** 按 Task 0 清单，将旧工程中每个 `BugFixStrategy` 等价类**逐文件复制**并注册到 `DEFAULT_STRATEGIES` 元组末尾（顺序：旧工程优先级在前或后，在清单中写明）。

- [ ] **Step 2:** 若旧工程通过子进程调用某 CLI，把完整命令写入 `docs/quickstart.md` 的「可选：全量自动修复」小节。

- [ ] **Step 3: Commit**

```bash
git add mcp/bug_fix_strategies.py docs/quickstart.md
git commit -m "feat(mcp): port legacy bug-fix strategies"
```

---

### Task 6: 文档与不变量一致化

**Files:**

- Modify: `docs/design/99-tools/14-mcp-core-invariants.md`
- Modify: `docs/mcp-basic-test-flow-reference-usage.md`
- Modify: `README.md`

- [ ] **Step 1: 替换不变量 §「能力与边界」相关条目**

将「自动修工具非串联默认环节」改为：

- **默认串联：** `run_game_basic_test_flow` / `run_game_basic_test_flow_by_current_state` 默认 `auto_repair=true`，在 `max_repair_rounds` 与 `auto_fix_max_cycles` 上限内交替复测。
- **显式关闭：** `auto_repair=false` 或 `GPF_AUTO_REPAIR_DEFAULT=0`。
- **编排工具：** 若保留，仅文档为别名；新集成应只使用 run 工具。

- [ ] **Step 2: 更新 `mcp-basic-test-flow-reference-usage.md` 第 4、7 节**

删除「高成本编排须显式同意」作为**唯一**修复路径的描述；改为「默认已包含修复；仅审计/CI 用 `auto_repair:false`」。

- [ ] **Step 3: Commit**

```bash
git add docs/design/99-tools/14-mcp-core-invariants.md docs/mcp-basic-test-flow-reference-usage.md README.md
git commit -m "docs: align invariants with default auto_repair semantics"
```

---

### Task 7: CI 与环境默认

**Files:**

- Modify: `.github/workflows/mcp-smoke.yml`
- Modify: `.github/workflows/mcp-integration.yml`

- [ ] **Step 1:** 在 workflow `env:` 中设置 `GPF_AUTO_REPAIR_DEFAULT: 0`，避免 CI 因策略误改示例工程；或在测试 `project_root` 的 JSON 中统一 `auto_repair:false`（二选一，全仓库一致）。

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/mcp-smoke.yml .github/workflows/mcp-integration.yml
git commit -m "ci: disable default auto_repair in MCP workflows"
```

---

## 执行完成记录（2026-04-11）

以下内容已在主仓库落地；与上文逐步骤复选框不必逐项手改，以本摘要与 git 为准。

- **Task 3：** `run_basic_test_flow_orchestrated` 改为委托 `run_game_basic_test_flow_by_current_state`（`auto_repair=true`，`max_orchestration_rounds` → `max_repair_rounds`）；`tests/test_flow_execution_runtime.py` 增加 `OrchestratedFlowDelegationTests`。
- **Task 4：** 新增 `mcp/repair_backend.py`；`run_bug_fix_loop` 增加 `l2_try_patch`；`server` 中 `auto_fix_game_bug` 传入 `build_l2_try_patch_from_env()`；`tests/test_repair_backend.py`；CI 的 unittest 列表包含 `tests.test_repair_backend`。
- **Task 5：** 未提供 `GPF_LEGACY_MCP_ROOT` 时未从旧仓复制策略；`docs/superpowers/notes/2026-04-10-legacy-mcp-parity-checklist.md` 已更新「本仓库当前」列。
- **Task 6：** 已更新 `docs/design/99-tools/14-mcp-core-invariants.md`、`docs/mcp-basic-test-flow-reference-usage.md`、`docs/mcp-real-runtime-input-contract-design.md` §8、`README.md`、`README.zh-CN.md`、`docs/mcp-docs-index.md`、`docs/quickstart.md` §6.5。
- **Task 7：** `.github/workflows/mcp-smoke.yml` 与 `mcp-integration.yml` 的 job 级 `GPF_AUTO_REPAIR_DEFAULT: "0"`。

---

## Self-review（计划作者自检）

1. **Spec coverage:** 用户要求「跑流程=完成预期修复闭环」「彻底方案」「旧工程已完美实现」→ Task 0 对照旧工程、Task 2 默认串联、Task 4 L2 可插拔、Task 5 迁移策略，均有对应任务。
2. **Placeholder scan:** 无 `TBD`；旧工程路径用环境变量 `GPF_LEGACY_MCP_ROOT` 指代，步骤中为具体 PowerShell 命令。
3. **Type consistency:** `run_flow_once_and_maybe_repair` 在 Task 1 为骨架；Task 2 扩展为 `run_multi_round_flow_repair` 时需保留相同 `final_status` 枚举或文档列出允许值，避免测试与实现漂移。

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-10-mcp-run-flow-default-auto-repair-unified.md`. Two execution options:**

**1. Subagent-Driven（推荐）** — 按 Task 0→7 逐 Task 派生子代理，Task 之间人工或主代理复核。

**2. Inline Execution** — 本会话内用 executing-plans 连续执行，按 Task 设置检查点。

**Which approach?**
