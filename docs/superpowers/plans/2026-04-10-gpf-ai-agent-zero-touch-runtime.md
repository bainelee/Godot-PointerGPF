# GPF AI 代理会话「零插拔」运行态与自动修复默认 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 **AI IDE / 代理会话** 中，用户只需完成「安装 GPF + 初始化工程上下文」等 **一次性工程侧前提**；**play_mode 门禁、桥接目录、自动修复默认** 应由 GPF + 代理工具链 **自动处理**，不得把「有 Godot/有工程却仍须用户手动按 F5 / 手动改 shell 环境关掉 CI 的 `GPF_AUTO_REPAIR_DEFAULT=0`」当作正常产品边界——除非存在 **可验证的硬不可行**（例如本机无任何 Godot 可执行文件候选、工程路径非法、用户显式禁止自动拉起引擎）。

**Architecture:** 引入 **会话画像（session profile）** 概念：在 **代理调用** 路径上，通过 **单次请求参数** 和/或 **专用环境变量** 声明「当前为 AI 代理会话」，使 `auto_repair` 默认值 **优先于** `GPF_AUTO_REPAIR_DEFAULT=0`（该变量保留给 **CI/批处理脚本** 显式降噪）；对 **play_mode bootstrap** 在代理会话下使用 **略更长的等待与可观测证据**，避免「编辑器已开但 Play 尚未稳定」被过早判死。文档侧 **拆分用户 README 与代理集成契约**，避免把代理责任误写成用户责任。

**Tech Stack:** Python 3.11、`mcp/server.py`、现有 `_ensure_runtime_play_mode` / `_parse_auto_repair_params`、`unittest`、`docs/`、可选 `.cursor/rules` 或 Cursor hooks、`.github/workflows/*`（仅澄清 CI 不注入代理会话变量）。

**Status（归档）：** Task 1–6 已在仓库落地（合并提交 `32d43ca`）；下文步骤复选框已勾选。Task 4 中「mock `_await_runtime_gate`」单测按计划 YAGNI 省略。

---

## 文件结构（落地前锁定）

| 文件 | 职责 |
|------|------|
| `mcp/server.py` | 解析 `agent_session` / `GPF_AGENT_SESSION_DEFAULTS`；调整 `_parse_auto_repair_params` 默认值逻辑；可选调整 `_ensure_runtime_play_mode` 在代理会话下的 `post_wait_ms` 下限 |
| `tests/test_agent_session_auto_repair_defaults.py`（新建） | 表驱动：环境 `GPF_AUTO_REPAIR_DEFAULT=0` + 代理会话开启时，省略 `auto_repair` 键仍应得到 `auto_repair=True` |
| `tests/test_flow_execution_runtime.py`（可选小改） | CLI 工具 schema 或 `get_adapter_contract` 若暴露新字段则加断言 |
| `docs/gpf-ai-agent-integration.md`（新建） | 代理集成契约：必须/禁止的环境变量、推荐 JSON 字段、与用户 README 的分工 |
| `docs/quickstart.md` | 用一小节指向代理集成文档；强调 **CI 与本地代理会话的差异** |
| `docs/mcp-basic-test-flow-reference-usage.md` | 增加「代理会话默认行为」交叉引用 |
| `.cursor/rules/*.mdc`（可选新建一条） | 在本仓库内由 Cursor 启动的终端/任务默认 `GPF_AGENT_SESSION_DEFAULTS=1`（不强制用户全局 shell） |

---

### Task 1: 失败用例 — `GPF_AUTO_REPAIR_DEFAULT=0` 且无 `auto_repair` 键

**Files:**

- Create: `tests/test_agent_session_auto_repair_defaults.py`
- Modify: （本 Task 仅测试，不修改实现）

- [x] **Step 1: 新建测试文件**

```python
"""Agent session overrides CI-style GPF_AUTO_REPAIR_DEFAULT=0 for implicit auto_repair default."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

import server  # noqa: E402


class TestAgentSessionAutoRepairDefaults(unittest.TestCase):
    @mock.patch.dict(os.environ, {"GPF_AUTO_REPAIR_DEFAULT": "0"}, clear=False)
    def test_without_agent_session_auto_repair_off(self) -> None:
        ar, _, _ = server._parse_auto_repair_params({})
        self.assertFalse(ar)

    @mock.patch.dict(os.environ, {"GPF_AUTO_REPAIR_DEFAULT": "0", "GPF_AGENT_SESSION_DEFAULTS": "1"}, clear=False)
    def test_with_env_agent_session_auto_repair_on(self) -> None:
        ar, _, _ = server._parse_auto_repair_params({})
        self.assertTrue(ar)

    @mock.patch.dict(os.environ, {"GPF_AUTO_REPAIR_DEFAULT": "0"}, clear=False)
    def test_with_argument_agent_session_auto_repair_on(self) -> None:
        ar, _, _ = server._parse_auto_repair_params({"agent_session_defaults": True})
        self.assertTrue(ar)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: 运行测试确认失败**

Run:

```powershell
Set-Location D:\AI\pointer_gpf
python -m unittest tests.test_agent_session_auto_repair_defaults -v
```

**预期:** `test_with_env_agent_session_auto_repair_on` 与 `test_with_argument_agent_session_auto_repair_on` **失败**（当前 `_parse_auto_repair_params` 未识别代理会话）。

- [x] **Step 3: Commit（测试红）**

```bash
git add tests/test_agent_session_auto_repair_defaults.py
git commit -m "test(mcp): agent session should override GPF_AUTO_REPAIR_DEFAULT=0"
```

---

### Task 2: 实现 `_effective_auto_repair_default` 并接入 `_parse_auto_repair_params`

**Files:**

- Modify: `mcp/server.py`（在 `_parse_auto_repair_params` 附近新增小函数并改分支）

- [x] **Step 1: 在 `mcp/server.py` 的 `_env_auto_repair_default` 下方增加**

```python
def _truthy_env(name: str) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return False
    return raw.strip() in ("1", "true", "True", "yes", "YES")


def _agent_session_defaults_requested(arguments: dict[str, Any]) -> bool:
    if bool(arguments.get("agent_session_defaults")):
        return True
    return _truthy_env("GPF_AGENT_SESSION_DEFAULTS")
```

- [x] **Step 2: 修改 `_parse_auto_repair_params` 的 `auto_repair` 分支**

将：

```python
    if "auto_repair" in arguments:
        auto_repair = bool(arguments.get("auto_repair"))
    else:
        auto_repair = _env_auto_repair_default()
```

替换为：

```python
    if "auto_repair" in arguments:
        auto_repair = bool(arguments.get("auto_repair"))
    elif _agent_session_defaults_requested(arguments):
        auto_repair = True
    else:
        auto_repair = _env_auto_repair_default()
```

**语义:** 显式 `auto_repair: false` 仍优先关闭；仅当 **未传** `auto_repair` 时，代理会话覆盖 `GPF_AUTO_REPAIR_DEFAULT=0`。

- [x] **Step 3: 运行 Task 1 测试**

Run:

```powershell
python -m unittest tests.test_agent_session_auto_repair_defaults -v
```

**预期:** 全部 PASS。

- [x] **Step 4: Commit**

```bash
git add mcp/server.py tests/test_agent_session_auto_repair_defaults.py
git commit -m "feat(mcp): agent session defaults override CI auto_repair off"
```

---

### Task 3: 工具 JSON Schema / 文档字符串暴露 `agent_session_defaults`

**Files:**

- Modify: `mcp/server.py` 中 `_build_tool_map` 或各 run 工具 schema 描述（搜索 `"auto_repair"` 的 `properties` 块）

- [x] **Step 1: 为 `run_game_basic_test_flow`、`run_game_basic_test_flow_by_current_state`（及若存在共用 schema 片段）增加属性**

在 JSON schema `properties` 中增加：

```json
"agent_session_defaults": {
  "type": "boolean",
  "description": "When true and auto_repair is omitted, force auto_repair default on even if env GPF_AUTO_REPAIR_DEFAULT=0 (AI agent sessions). CI should not set this."
}
```

- [x] **Step 2: 运行现有 MCP 相关单测**

Run:

```powershell
python -m unittest tests.test_flow_execution_runtime.McpToolSchemaTests -v
```

**预期:** PASS（若测试扫描 schema 字段数量，按需同步断言）。

- [x] **Step 3: Commit**

```bash
git add mcp/server.py
git commit -m "docs(mcp): document agent_session_defaults on run tools"
```

---

### Task 4（可选但推荐）: 代理会话下略延长 play_mode bootstrap 等待

**Files:**

- Modify: `mcp/server.py` 中 `_ensure_runtime_play_mode`

- [x] **Step 1: 在计算 `post_wait_ms` 之前读取代理会话**

```python
agent_session = _agent_session_defaults_requested(arguments)
```

- [x] **Step 2: 调整 `post_wait_ms` 下限**

将：

```python
    post_wait_ms = 18_000 if bootstrap["launch_succeeded"] or bootstrap["editor_running_before_launch"] else 1_500
```

改为（示例，可微调数值）：

```python
    base_post = 18_000 if bootstrap["launch_succeeded"] or bootstrap["editor_running_before_launch"] else 1_500
    post_wait_ms = int(max(base_post, 24_000 if agent_session else base_post))
```

**说明:** 不在代理会话改变失败语义，仅减少「已拉起/已开编辑器但 gate 尚未写入」的误杀。

- [x] **Step 3: 单测**

在 `tests/test_agent_session_auto_repair_defaults.py` 或新建 `tests/test_agent_session_play_bootstrap_timing.py` 中 **mock** `_await_runtime_gate`，断言第二次调用时的 `timeout_ms` ≥ 24000（当 `agent_session_defaults=True` 且 `launch_succeeded=True`）。若 mock 成本过高，可改为只测 **私有辅助函数** 提取 `post_wait_ms` 计算（YAGNI：若提取函数过大，本 Task 可标为可选跳过，仅保留文档说明）。

- [x] **Step 4: Commit**

```bash
git add mcp/server.py tests/test_agent_session_auto_repair_defaults.py
git commit -m "feat(mcp): longer play_mode gate wait under agent session"
```

---

### Task 5: 代理集成契约文档（与用户 README 分工）

**Files:**

- Create: `docs/gpf-ai-agent-integration.md`
- Modify: `docs/quickstart.md`、`docs/mcp-basic-test-flow-reference-usage.md`

- [x] **Step 1: 撰写 `docs/gpf-ai-agent-integration.md` 必备小节**

1. **用户一次性义务**：安装插件、`init_project_context`、提供正确 `project_root`、本机存在可发现的 Godot（或配置 `godot_executable`）。  
2. **代理义务**：调用 run 工具时 **省略 `auto_repair` 则必须**（二选一）设置环境变量 `GPF_AGENT_SESSION_DEFAULTS=1`，或传 `"agent_session_defaults": true`；**不得**要求用户手动 F5。  
3. **CI 义务**：工作流 **不得**设置 `GPF_AGENT_SESSION_DEFAULTS`；保留 `GPF_AUTO_REPAIR_DEFAULT=0` 降噪。  
4. **仍属硬失败的情形**：`no_executable_candidates`、`temp_project_autostart_blocked`、用户 `disable_engine_autostart: true` —— 返回体中已有 `engine_bootstrap` / `blocking_point`，代理应据此自动重试或改配置，而非转嫁给终端用户「你去按 Play」。

- [x] **Step 2: 在 `docs/quickstart.md` 的 6.5 节附近加一句链接**

指向 `docs/gpf-ai-agent-integration.md`。

- [x] **Step 3: 在 `docs/mcp-basic-test-flow-reference-usage.md` 的自动修复小节加交叉引用**

- [x] **Step 4: Commit**

```bash
git add docs/gpf-ai-agent-integration.md docs/quickstart.md docs/mcp-basic-test-flow-reference-usage.md
git commit -m "docs: AI agent session contract vs user/CI responsibilities"
```

---

### Task 6（可选）: Cursor 规则 — 仓库内终端默认注入 `GPF_AGENT_SESSION_DEFAULTS`

**Files:**

- Create: `.cursor/rules/gpf-agent-session-env.mdc`（或等价命名）

- [x] **Step 1: 规则正文（示例）**

```markdown
---
description: 在本仓库通过 Cursor 执行任务时，为 MCP/CLI 子进程声明 GPF 代理会话默认行为
alwaysApply: false
globs: []
---

当运行 `python mcp/server.py` 或执行与 `run_game_basic_test_flow*` 相关的自动化时，若 shell 由 Cursor 启动，应设置环境变量 `GPF_AGENT_SESSION_DEFAULTS=1`，除非用户明确处于「模拟 CI」场景。
```

- [x] **Step 2: Commit**

```bash
git add .cursor/rules/gpf-agent-session-env.mdc
git commit -m "chore(cursor): suggest GPF_AGENT_SESSION_DEFAULTS for agent shells"
```

---

## Self-review

**1. Spec coverage（对照用户诉求）**

| 诉求 | 对应 Task |
|------|-----------|
| `GPF_AUTO_REPAIR_DEFAULT=0` 不应在代理会话静默关闭自动修复 | Task 2（`GPF_AGENT_SESSION_DEFAULTS` + `agent_session_defaults`） |
| play_mode / 门禁应由产品侧尽量自动完成，不甩锅用户按 F5 | Task 4（延长等待）+ Task 5 文档明确代理须用会话标志并解读 `engine_bootstrap`） |
| 用户只负责「插头」级安装/初始化 | Task 5 用户 vs 代理分工 |
| CI 仍需关闭噪音 | Task 5 明确 CI 不注入代理变量；`GPF_AUTO_REPAIR_DEFAULT=0` 仍有效当 **未** 声明代理会话 |

**2. Placeholder 扫描**

- 无 `TBD` / 空实现步骤；Task 4 单测若过重允许跳过并已在 Step 3 写明 YAGNI 分支。

**3. 类型与命名一致性**

- 环境变量名 `GPF_AGENT_SESSION_DEFAULTS` 与 JSON 字段 `agent_session_defaults` 并存：文档中应用表格对照，避免后续 Task 改名漂移。

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-10-gpf-ai-agent-zero-touch-runtime.md`.**

**已选方案 1（Subagent-Driven）并完成实现**（合并提交 `32d43ca`）：含 `GPF_AGENT_SESSION_DEFAULTS` / `agent_session_defaults`、schema、play_mode 等待下限、文档、Cursor 规则与 CI 测试列表。
