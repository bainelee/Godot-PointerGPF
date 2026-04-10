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
