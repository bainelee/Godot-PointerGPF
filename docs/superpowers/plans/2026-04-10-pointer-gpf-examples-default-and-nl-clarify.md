# pointer_gpf 仓库内「示例项目」默认 + 自然语言跑流程前的易读澄清 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 **本仓库 `pointer_gpf` 内** 对话时，用户口中的「跑一遍 examples/示例项目」**唯一默认**指向 **`examples/godot_minimal`**（MCP 开发辅助用 Godot 工程）；当用户用自然语言要求「跑一遍基础测试流程」等时，**禁止**把 **`GPF_AGENT_SESSION_DEFAULTS`** 等实现细节当作用户必读前提；代理应在 **发起 MCP 调用前** 使用 **清晰中文的 AskQuestion**（或等价交互）让用户选择「失败时是否自动尝试修复」，选项文案与后续 JSON 参数的映射关系写死在文档与规则中。

**Architecture:** 以 **`alwaysApply` 的 Cursor 规则** + **全局沟通规则增补** 锁定「示例项目」词义；新建 **面向代理的操作剧本** Markdown，内含 **可复制** 的 AskQuestion `prompt` / `options[].label` 全文及与 `auto_repair` / `agent_session_defaults` 的映射；**不**把环境变量名写进面向用户的选项标题。可选：在 **`mcp/nl_intent_router.py`** 或 **`route_nl_intent` 工具返回体** 增加 `default_example_project_root` 只读提示字段（相对 `repo_root`），减少代理猜路径。

**Tech Stack:** Markdown、`.cursor/rules/*.mdc`、`docs/`、`mcp/server.py`（若做可选字段）、`tests/test_nl_intent_router_expanded.py`（若改路由返回）、`unittest`。

**Status（归档）：** Task 1–5 已在仓库落地；下文步骤复选框已勾选。

---

## 文件结构（落地前锁定）

| 文件 | 职责 |
|------|------|
| `.cursor/rules/global-communication-terminology.mdc` | 增补一节：**本仓库内「示例项目」= `examples/godot_minimal`** |
| `docs/gpf-nl-basic-flow-clarifying-questions.md`（新建） | AskQuestion 固定文案 + 选项与 MCP 参数的映射表（中文，无环境变量黑话） |
| `docs/gpf-ai-agent-integration.md` | 将「环境变量」降级为附录；正文强调 **先问用户再调工具** |
| `.cursor/rules/gpf-ask-before-basic-flow-run.mdc`（新建，`alwaysApply: true`） | 强制：自然语言命中跑基础流程意图且未显式传参时，先 AskQuestion 再 `tools/call` |
| `mcp/server.py`（可选） | `_tool_route_nl_intent` 返回中增加 `canonical_example_project_rel` 等只读字段 |
| `tests/test_nl_intent_router_expanded.py`（可选） | 若改 server 返回字段则加断言 |

---

### Task 1: 全局沟通规则 — 锁定「示例项目」词义

**Files:**

- Modify: `.cursor/rules/global-communication-terminology.mdc`

- [x] **Step 1: 在「## 1. 适用范围」之后插入新小节「## 1.1 本仓库内「示例 / examples 工程」默认所指」**

插入全文（保持 UTF-8，列表用 `-`）：

```markdown
## 1.1 本仓库内「示例 / examples 工程」默认所指

- 只要对话上下文仍在本仓库 **`pointer_gpf`**（本工作区根目录含本规则与 `examples/` 目录），用户说 **「跑示例项目」「跑 examples 里的项目」「跑示例 Godot 工程」** 等，**默认且唯一** 指：`examples/godot_minimal/` 下的 Godot 工程（该目录含 `project.godot`，用于辅助本 MCP 开发与回归）。
- **除非**用户同时给出 **其它明确的绝对路径** 或写明「不是 minimal 示例」，否则代理不得将「示例」解释为工作区外任意 Godot 工程。
- 进度反馈中应写出 **`examples/godot_minimal`** 或其在磁盘上的绝对路径，避免仅用「你的示例工程」等模糊说法。
```

- [x] **Step 2: Commit**

```bash
git add .cursor/rules/global-communication-terminology.mdc
git commit -m "docs(rules): default examples project to examples/godot_minimal"
```

---

### Task 2: 新建《自然语言跑流程前澄清问题》剧本（含 AskQuestion 映射）

**Files:**

- Create: `docs/gpf-nl-basic-flow-clarifying-questions.md`

- [x] **Step 1: 写入下列完整内容（可按需微调措辞，不得删除映射表）**

```markdown
# 自然语言「跑基础测试流程」前的澄清（给代理复制用）

## 何时必须提问

当用户自然语言意图经 `route_nl_intent` 指向 **`run_game_basic_test_flow_by_current_state`** 或 **`run_game_basic_test_flow`**，且用户 **没有** 同时说明「失败时不要自动改工程」之类明确偏好时，代理应在 **第一次** 调用 MCP 跑流程 **之前** 发起一次澄清（Cursor 使用 **AskQuestion**；其它客户端使用等价单选题）。

## 禁止对用户说的内容

- 不要要求用户理解或手动设置 **`GPF_AGENT_SESSION_DEFAULTS`**、**`GPF_AUTO_REPAIR_DEFAULT`** 等环境变量名（可放在开发者文档附录）。
- 不要把「打开 Play」写成用户操作步骤；若门禁失败，应复述工具返回的 **`blocking_point` / `next_actions`**，由代理决定是否重试或改配置。

## AskQuestion 推荐文案（中文）

**问题 id：** `basic_flow_failure_behavior`

**提示语（prompt）：**

> 接下来要在本机的 Godot 工程里「跑一遍基础测试流程」（真实进入可玩状态再跑步骤）。若某一步失败，你希望我怎么处理？

**选项（必须两项，且顺序固定）：**

| option id | 展示给用户的文案（label） | 代理后续 MCP 行为 |
|-----------|---------------------------|-------------------|
| `auto_try_fix` | **失败时自动尝试修复并重试**（会按内置规则修改工程或写入提示文件，有轮次上限；适合日常开发） | 调用 run 工具时在 `--args` JSON 中传 **`"agent_session_defaults": true`**，且 **不传** `auto_repair` 键；若 shell 继承了 CI 的关自动修环境，仍保持「会尝试修」。 |
| `run_only` | **只运行、失败时不要自动改工程**（适合你想先看原始错误） | 在 `--args` JSON 中显式传 **`"auto_repair": false`**。 |

用户选择后，代理在回复中用 **一句话** 复述用户选择（用 label 原文，不要改成环境变量名）。

## 与本仓库「示例项目」的默认路径配合

若用户说「跑示例 / examples」而未给 `project_root`，默认使用：

`{REPO_ROOT}/examples/godot_minimal`

其中 `{REPO_ROOT}` 为当前 `pointer_gpf` 仓库根目录（Windows 示例：`D:/AI/pointer_gpf/examples/godot_minimal`）。
```

- [x] **Step 2: Commit**

```bash
git add docs/gpf-nl-basic-flow-clarifying-questions.md
git commit -m "docs: NL basic flow AskQuestion playbook for agents"
```

---

### Task 3: 强制规则 — 跑流程前先 AskQuestion

**Files:**

- Create: `.cursor/rules/gpf-ask-before-basic-flow-run.mdc`

- [x] **Step 1: 写入 frontmatter + 正文**

```markdown
---
description: 自然语言要求跑基础测试流程时，先用中文 AskQuestion 澄清失败时是否自动修复，禁止对用户口述环境变量名
alwaysApply: true
---

# 跑基础测试流程前的交互（强制）

1. **本仓库内「示例项目」**：用户未指定其它路径时，`project_root` 使用 **`examples/godot_minimal`** 的绝对路径（见 `global-communication-terminology.mdc` §1.1）。
2. 当用户自然语言触发 **`run_game_basic_test_flow`** / **`run_game_basic_test_flow_by_current_state`**（含经 `route_nl_intent` 路由），且用户 **尚未** 明确说「不要自动修 / 只跑不修」或「要自动修」时：必须先使用 **AskQuestion**，文案与选项严格采用 **`docs/gpf-nl-basic-flow-clarifying-questions.md`** 中的 **prompt** 与 **两档 label**。
3. 得到用户选项后，再构造 MCP `tools/call` 的 `arguments`：**禁止**在面向用户的句子中出现 `GPF_AGENT_SESSION_DEFAULTS`；实现侧映射见该文档表格。
4. 若用户在同一条消息里已明确二选一（与表格语义等价），可跳过 AskQuestion，但须在回复中 **复述** 用户选择。
```

- [x] **Step 2: Commit**

```bash
git add .cursor/rules/gpf-ask-before-basic-flow-run.mdc
git commit -m "chore(cursor): require AskQuestion before basic flow MCP run"
```

---

### Task 4: 修订 `docs/gpf-ai-agent-integration.md` — 用户可读优先

**Files:**

- Modify: `docs/gpf-ai-agent-integration.md`

- [x] **Step 1: 在文首「## 1」之前增加引导段**

```markdown
> **给终端用户：** 你不需要记住任何环境变量名。用自然语言说「跑一遍基础测试流程」时，助手会先问你一个 **二选一** 的问题（见 `docs/gpf-nl-basic-flow-clarifying-questions.md`）。下面「环境变量」小节主要给 **CI 与脚本集成方** 阅读。
```

- [x] **Step 2: 将原「## 2」标题改为「## 2（集成方）代理如何覆盖 CI 的关自动修」**，并在该节首句增加链接：「终端用户请优先走 **`docs/gpf-nl-basic-flow-clarifying-questions.md`**。」

- [x] **Step 3: Commit**

```bash
git add docs/gpf-ai-agent-integration.md
git commit -m "docs: lead users to AskQuestion playbook before env vars"
```

---

### Task 5（可选）: `route_nl_intent` 返回体增加只读 `canonical_example_project_root`

**Files:**

- Modify: `mcp/server.py` 中 `_tool_route_nl_intent` 的返回 dict
- Modify: `tests/test_nl_intent_router_expanded.py` 或新增 CLI 测试

- [x] **Step 1: 在 `_tool_route_nl_intent` 返回中增加字段**

```python
    return {
        "text": text,
        "target_tool": routed.target_tool,
        "reason": routed.reason,
        "canonical_example_project_root": str((ctx.repo_root / "examples" / "godot_minimal").resolve()),
        "canonical_example_project_rel": "examples/godot_minimal",
    }
```

（若 `ServerCtx` 无 `repo_root`，改用与 `get_adapter_contract` 相同的根路径解析方式。）

- [x] **Step 2: 单测**

在 `tests/test_nl_intent_router_expanded.py` 中增加：mock `ctx.repo_root`，调用 `_tool_route_nl_intent`，断言返回含 `canonical_example_project_rel == "examples/godot_minimal"`。

- [x] **Step 3: Commit**

```bash
git add mcp/server.py tests/test_nl_intent_router_expanded.py
git commit -m "feat(mcp): route_nl_intent hints canonical example project path"
```

---

## Self-review

| 用户要求 | 覆盖 Task |
|----------|-----------|
| 本仓库内「示例/examples」= 专门测试工程 | Task 1 §1.1 + Task 2 文档路径段 + Task 3 规则第 1 条 |
| 不说 `GPF_AGENT_SESSION_DEFAULTS` 给用户听；用自然语言后 AskQuestion | Task 2 映射表 + Task 3 + Task 4 |
| 选项清晰易读 | Task 2 表格内 **label** 为完整中文句 |

**Placeholder 扫描：** 无 `TBD`。

**类型一致性：** `option id` 与规则中「两档」一致；MCP JSON 键名 `agent_session_defaults` / `auto_repair` 与现有 `mcp/server.py` 一致。

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-10-pointer-gpf-examples-default-and-nl-clarify.md`.**

**已选方案 1（Subagent-Driven）并完成实现**（含 Task 5：`route_nl_intent` 返回示例工程路径字段）。
