# Auto 模式下 Superpowers 合规与防推卸责任 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐步实施。步骤使用复选框（`- [ ]`）语法跟踪进度。

**Goal:** 在 Cursor Auto 等「弱约束」运行态下，用仓库内可版本化、可测试的契约（`AGENTS.md` + 常驻规则 + 契约测试）降低 agent 跳过 superpowers 流程、推卸责任和污染上下文的概率；无法 100% 改变模型倾向，但可把违规变成「可发现、可回滚、可 CI 拦截」的工程问题。

**Architecture:** Superpowers 技能文档写明 **用户显式指令（含 `AGENTS.md`）优先级高于技能本身**。因此在仓库根目录增加具有法律效力的短契约 `AGENTS.md`，内容与现有 `.cursor/rules` 对齐并强制「先技能后动作」「证据先于结论」「失败输出 blocking_point/next_actions」。再用 `alwaysApply: true` 的 Cursor 规则把同一套机械清单压到每次模型可见上下文。最后用 `unittest` 断言关键文件与锚点字符串存在，防止误删或空心化。可选：在用户本机配置 Cursor Hooks，在每次对话轮次注入一行自检提醒（不进入仓库，避免团队环境差异）。

**Tech Stack:** Markdown、Cursor Rules（`.mdc`）、Python 3.11、`unittest`、Git。

---

## 拟创建/修改的文件与职责

| 路径 | 职责 |
| --- | --- |
| `AGENTS.md`（仓库根） | 对本仓库 agent 的最高优先级显式约束：技能调用顺序、自检清单、禁止推卸责任的表述标准、与 GPF 运行态规则的引用关系。 |
| `.cursor/rules/agent-auto-mode-gates.mdc` | `alwaysApply`，每次对话可见的短清单（机械步骤），与 `AGENTS.md` 重复有意为之：双通道提高 Auto 模式命中率。 |
| `tests/test_agent_workspace_contract.py` | 契约测试：文件存在性 + 必需章节/锚点字符串；被删或改坏即 CI/本地测试失败。 |
| （可选，仅用户本机）`.cursor/hooks.json` + 钩子脚本 | 每轮用户消息前注入固定提醒；路径不在仓库内统一提交，计划中给出完整可复制示例。 |

---

### Task 1: 契约测试（先失败）

**Files:**
- Create: `tests/test_agent_workspace_contract.py`
- Modify: （无）
- Test: `tests/test_agent_workspace_contract.py`

- [ ] **Step 1: 编写会先失败的契约测试**

```python
"""仓库级 agent 契约：防止 Auto 模式下误删关键治理文件。"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class TestAgentWorkspaceContract(unittest.TestCase):
    def test_agents_md_has_binding_sections(self) -> None:
        path = REPO / "AGENTS.md"
        self.assertTrue(path.is_file(), "缺少仓库根目录 AGENTS.md")
        text = path.read_text(encoding="utf-8")
        for needle in (
            "## 指令优先级",
            "## 每轮强制自检（机械清单）",
            "## 禁止推卸责任",
            "## 与仓库规则的关系",
        ):
            self.assertIn(needle, text, f"AGENTS.md 缺少章节锚点: {needle}")

    def test_auto_mode_gates_rule_exists(self) -> None:
        path = REPO / ".cursor" / "rules" / "agent-auto-mode-gates.mdc"
        self.assertTrue(path.is_file(), "缺少 .cursor/rules/agent-auto-mode-gates.mdc")
        text = path.read_text(encoding="utf-8")
        self.assertIn("alwaysApply: true", text)
        for needle in (
            "先读取并遵循",
            "verification-before-completion",
            "blocking_point",
            "next_actions",
        ):
            self.assertIn(needle, text, f"规则文件缺少锚点: {needle}")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_agent_workspace_contract -v`

Expected: `FAIL`（`AssertionError: False is not true : 缺少仓库根目录 AGENTS.md` 或缺少规则文件）

- [ ] **Step 3: 提交仅测试文件（红灯）**

```bash
git add tests/test_agent_workspace_contract.py
git commit -m "test: add agent workspace contract (expected fail)"
```

---

### Task 2: 添加 `AGENTS.md`（最高优先级显式契约）

**Files:**
- Create: `AGENTS.md`（仓库根）
- Modify: （无）
- Test: `tests/test_agent_workspace_contract.py`（`test_agents_md_has_binding_sections` 应变绿）

- [ ] **Step 4: 写入完整的 `AGENTS.md`**

```markdown
# 本仓库 Agent 显式契约（优先级最高）

本文档与 Cursor User Rules、`.cursor/rules` 共同约束本仓库内的自动化开发行为。
若与 superpowers 技能文本冲突，**以本文档与用户显式指令为准**；若本文档与 `.cursor/rules` 冲突，**以本文档为准**。

## 指令优先级

1. 用户在本对话中的明确指令（含本文件）
2. superpowers 与各域技能（必须通过阅读技能文件内容执行，禁止凭记忆省略）
3. 模型默认行为

## 每轮强制自检（机械清单）

在**每一次**准备调用工具或给出结论之前，必须在内心完成下列检查，并在用户可见回复中**至少用一句话声明**当前回合覆盖了哪一条（例如：「本回合已按 verification-before-completion 要求运行了 unittest」）：

1. **技能门闩**：若任务属于调试 / 写计划 / 写测试 / 验收完成 / 并行分派 / 头脑风暴等 superpowers 已覆盖类型，必须先读取对应 `SKILL.md` 再动手；禁止用「我记得流程」替代。
2. **证据先于结论**：声称测试通过、问题已修复、流程已跑通时，必须已运行对应命令并能在回复中复述关键输出（或指向日志路径）；禁止无命令输出的「已完成」。
3. **GPF 运行态**：凡用户要求「跑一次流程」或 GPF 测试流程，遵守 `.cursor/rules/gpf-runtime-test-mandatory-play-mode.mdc`：真实 play_mode、同步等待、失败时给出 `blocking_point` 与 `next_actions`。
4. **沟通用语**：遵守 `.cursor/rules/global-communication-terminology.mdc`：先事实后判断；禁用该文件中列出的黑话替代句式。
5. **上下文卫生**：优先用工具读取文件而非粘贴大段代码；同一结论不在对话中重复冗长表述；长背景写入仓库内文档并在对话中给路径。

## 禁止推卸责任

下列句式视为违规，除非同时给出**已执行的排查命令与输出摘要**：

- 将失败主要归因于「用户未操作」「用户环境」而未说明系统侧已尝试的自动化步骤上限。
- 在未读取 `pointer_gpf/tmp/runtime_diagnostics.json`（若存在）等约定证据前，断言「无法继续」。

合规失败陈述格式必须为：

- `blocking_point`：当前阻塞的具体条件（可验证）
- `next_actions`：下一步由 agent 或用户执行的**单一**明确动作
- `已执行`：本轮已运行的命令/工具及其结果摘要

## 与仓库规则的关系

- `.cursor/rules/` 下文件为 Cursor 注入的常驻规则；本文件为显式最高优先级补充。
- 若 Auto 模式未显示某条规则，仍以本文件与技能全文为准。

## Superpowers 引用名（便于检索）

执行计划类任务时优先使用：`superpowers:subagent-driven-development`、`superpowers:executing-plans`、`superpowers:verification-before-completion`、`superpowers:systematic-debugging`、`superpowers:test-driven-development`、`superpowers:writing-plans`。
```

- [ ] **Step 5: 运行测试**

Run: `python -m unittest tests.test_agent_workspace_contract.TestAgentWorkspaceContract.test_agents_md_has_binding_sections -v`

Expected: `PASS`

- [ ] **Step 6: 提交**

```bash
git add AGENTS.md
git commit -m "docs(agents): add binding agent contract for auto mode"
```

---

### Task 3: 添加常驻 Cursor 规则 `agent-auto-mode-gates.mdc`

**Files:**
- Create: `.cursor/rules/agent-auto-mode-gates.mdc`
- Modify: （无）
- Test: `tests/test_agent_workspace_contract.py::test_auto_mode_gates_rule_exists`

- [ ] **Step 7: 创建规则文件（完整内容）**

```markdown
---
description: Auto 模式机械门闩：技能、证据、失败格式、上下文卫生
alwaysApply: true
---

# Agent Auto 模式门闩（与 AGENTS.md 同步）

## 执行顺序（不可跳过）

1. 若任务可能适用 superpowers 技能：必须先读取对应 `SKILL.md` 再使用工具或改代码。
2. 若声称完成/通过验证：必须先运行 `superpowers:verification-before-completion` 所要求的验证命令（或等价项目命令），再写结论。
3. 若用户要求 GPF 流程：必须遵守 `gpf-runtime-test-mandatory-play-mode` 规则全文。

## 回复中必须遵守

- **证据先于结论**：结论中引用已运行的命令与结果摘要（或日志路径）。
- **失败格式**：含 `blocking_point`、`next_actions`、已执行排查（与 `AGENTS.md` 一致）。
- **禁止推卸**：不得在无证据时把失败主因归于用户；说明自动化已尝试的步骤上限。
- **上下文卫生**：少贴大段代码；长内容写入仓库文件并给路径。

## 锚点（供契约测试检索）

先读取并遵循 verification-before-completion；blocking_point；next_actions。
```

- [ ] **Step 8: 运行完整契约测试**

Run: `python -m unittest tests.test_agent_workspace_contract -v`

Expected: 两条测试均 `PASS`

- [ ] **Step 9: 提交**

```bash
git add .cursor/rules/agent-auto-mode-gates.mdc
git commit -m "chore(cursor): add always-on auto mode gates rule"
```

---

### Task 4（可选）: 用户本机 Cursor Hook 注入

**Files:**
- Create: 仅用户本机，例如 `%USERPROFILE%\.cursor\hooks.json`（Windows）或项目外路径；**默认不提交到 Git**。
- Modify: （无）
- Test: 手动验证：新开对话首条模型回复是否体现门闩提醒。

- [ ] **Step 10: 在用户本机添加 hook（示例，按 Cursor 当前 hooks 文档调整事件名）**

若你使用的 Cursor 版本支持 `beforeSubmitPrompt` 或等价事件，可使用下列结构（事件键名以官方文档为准，计划中为示例）：

`hooks.json`：

```json
{
  "version": 1,
  "hooks": {
    "beforeSubmitPrompt": [
      {
        "command": "python",
        "args": ["-c", "print('[agent-gate] 先读 AGENTS.md 与相关 superpowers SKILL；证据先于结论；失败写 blocking_point/next_actions。')"]
      }
    ]
  }
}
```

Expected: 用户每次提交提示前，终端/日志出现一行固定提醒，降低「忘记门闩」概率。

- [ ] **Step 11: 不提交 hook 文件；若团队需要，仅在内部文档记录路径与用途**

---

## 自检（计划作者执行，非子任务）

**1. Spec coverage：** 用户诉求「不遵守 superpowers」「推卸责任」「污染上下文」分别映射到：技能门闩 + verification + `AGENTS.md` 优先级；禁止推卸与强制失败格式；上下文卫生与少贴代码。可选 hook 增强提醒。

**2. Placeholder scan：** 无 TBD；hook 事件名已标注以官方文档为准。

**3. Type consistency：** 测试锚点与 `AGENTS.md`、`.mdc` 中字符串一致。

---

## 执行交接

计划已保存到 `docs/superpowers/plans/2026-04-11-auto-mode-superpowers-compliance.md`。可选执行方式：

**1. Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间人工抽查。

**2. Inline Execution** — 本会话用 executing-plans 连续执行并设检查点。

**你希望采用哪一种？**
