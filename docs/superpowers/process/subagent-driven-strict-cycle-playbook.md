# 严格子代理循环：每 Task 独立实现者 + 规格审查 + 代码审查

本页约定在 Cursor 中执行 **`docs/superpowers/plans/2026-04-11-automated-test-game-window-teardown-hard-guarantee.md`**（或其它带 Task checkbox 的计划）时，**禁止**由主会话一口气改完再自称审查通过；改为**每个 Task** 固定三轮 **独立子代理**（新上下文），顺序不可调换。

## 角色与顺序（不可跳过）

1. **实现者（Implementer）** — 只读主控粘贴的「Task 全文 + 场景上下文」，**不得**自行打开计划文件（避免漏读/误读）。产出：代码改动、测试命令与结果、自评、可选 `git commit`。
2. **规格审查（Spec compliance）** — **在规格通过前禁止进入代码质量审查。** 不信任实现者口头报告；必须对照需求逐条读**实际 diff/文件**。
3. **代码质量审查（Code quality）** — 仅在规格审查 ✅ 后派发；关注可维护性、边界、测试是否测到行为而非仅 mock。

提示词母版见本机 superpowers 插件目录（勿手抄走样，派发时从文件复制）：

- `.../skills/subagent-driven-development/implementer-prompt.md`
- `.../skills/subagent-driven-development/spec-reviewer-prompt.md`
- `.../skills/subagent-driven-development/code-quality-reviewer-prompt.md`

## 主控（编排者）每次派发的最小信息包

### 给实现者

- `Task` → `subagent_type: generalPurpose`（机械实现可用 `model: fast`）
- `prompt` 内包含：**Task 标题、计划里该 Task 的完整 Markdown（含步骤与代码块）、工作区根路径、禁止范围、验收命令**

### 给规格审查者

- `Task` → `subagent_type: generalPurpose`（建议比实现者略强或同级）
- `prompt` 内包含：**该 Task 的完整需求原文、实现者报告全文、要求审查者自行 `read`/`grep` 相关路径并给出 ✅ 或 ❌ 与文件:行号**

### 给代码质量审查者

- `Task` → `subagent_type: code-reviewer`
- `prompt` 内包含：**本 Task 改动摘要、涉及文件路径、BASE_SHA/HEAD_SHA（若已 commit）、计划 Task 标题**

## 硬规则（与 superpowers 技能一致）

- **同一时刻只派一个实现者**，避免多写冲突。
- 规格审查 ❌ → 回到**同一 Task** 的实现者修复 → 再派规格审查，直到 ✅。
- 代码质量审查有 Important/Critical → 实现者修复 → **仅**再派代码质量审查（规格未变则不必重跑规格，除非修复引入行为变化）。

## 与「游戏测试窗口收尾」计划的 Task 映射

| Task | 实现者主要交付物 |
|------|------------------|
| 1 | `examples/godot_minimal/addons/pointer_gpf/` 与模板同源 + `tests/test_examples_minimal_pointer_gpf_addon_tracked.py` |
| 2 | `mcp/server.py` 中 ack 后 gate 轮询与二次 `closeProject` + `tests/test_mcp_hard_teardown.py` |
| 3 | `plugin.gd` 成功 teardown JSON + `mcp/server.py` `_attach_teardown_*` + 测试 |
| 4 | `tests/test_basic_flow_run_only_still_closes_play.py` |
| 5 | `docs/superpowers/notes/2026-04-11-game-window-teardown-manual-acceptance.md`（人工步骤可标为 DONE_WITH_CONCERNS 并附证据路径） |
| 6 | `_hard_teardown_for_flow_failure` 分支 + 单测 |

主控在**每个 Task 的三轮都结束**后，再在计划 Markdown 里勾选该 Task 的 checkbox（若仓库政策允许改计划文件）。

---

## 防死循环：主控派发实现者时必须写死的约束（重要）

此前有案例：实现者子代理在全量 `unittest discover` +「失败就改到通过」指令下**长时间运行或反复重试**，用户只得中止任务。根因通常是：

1. **全量 discover** 含 `test_flow_execution_runtime` 等**子进程 / 长超时**用例，单次可跑 **数十分钟**，子代理误判为「卡住」而重复执行或盲目改代码。  
2. **未设修复次数上限**，同一失败点在多轮中重复相同修改。  
3. **未设单命令超时**，Shell 一直等待无输出。

**主控在 prompt 里必须显式包含（复制即用）：**

- **单次验收优先用「窄命令」**，与当前 Task 文件相关即可，例如：
  - `python -m unittest tests.test_mcp_hard_teardown tests.test_runtime_gate_marker_plugin -v`
  - 或计划 §6 中写明的模块列表；**避免**让子代理在无上限条件下跑完整 `discover`。
- 若必须跑全量：写明 **「只运行一次；若超过 30 分钟无完整摘要则 Status=BLOCKED，禁止再次启动 discover」**，并建议主控在本机用**有 wall-clock 的终端**跑全量，子代理只做**窄测**。
- **修复轮次上限**：`最多自行修复并重跑 2 轮；仍失败则 Status=BLOCKED，输出失败用例全名与最后一屏 stderr`。
- **禁止循环**：`禁止在未阅读失败日志的情况下重复同一命令超过 3 次`；`禁止同时起多个 discover`。

**规格/代码审查子代理**：只做只读审查与列表结论，**不要**派它们去跑全量 discover（避免再次拖死）。

用户中止任务时，主控应记录：**中止原因（例如长时间无输出 / 疑似重复命令）**，下一轮子代理 prompt 中附带，避免重复踩坑。
