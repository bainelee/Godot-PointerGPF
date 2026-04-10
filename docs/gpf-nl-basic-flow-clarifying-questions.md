# 自然语言「跑基础测试流程」前的澄清（给代理复制用）

## 何时必须提问

当用户自然语言意图经 `route_nl_intent` 指向 **`run_game_basic_test_flow_by_current_state`** 或 **`run_game_basic_test_flow`**，且用户 **没有** 同时说明「失败时不要自动改工程」或「只跑不修」或对称地明确「失败时要自动修」之类偏好时，代理应在 **第一次** 调用 MCP 跑流程 **之前** 发起一次澄清（在 Cursor 中使用 **AskQuestion**；其它客户端使用等价单选题）。

## 禁止对用户说的内容

- 不要要求用户理解或手动设置 **`GPF_AGENT_SESSION_DEFAULTS`**、**`GPF_AUTO_REPAIR_DEFAULT`** 等环境变量名（这些仅写在 **`docs/gpf-ai-agent-integration.md`** 供 CI / 脚本集成方阅读）。
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

用户选择后，代理在回复中用 **一句话** 复述用户选择（用 label 里的可读中文，不要改成环境变量名）。

## 与本仓库「示例项目」的默认路径配合

若用户说「跑示例 / examples」而未给 `project_root`，默认使用本仓库下的：

`examples/godot_minimal`

绝对路径为：`{仓库根}/examples/godot_minimal`（Windows 示例：`D:/AI/pointer_gpf/examples/godot_minimal`）。

调用 `route_nl_intent` 工具时，返回体中的 **`canonical_example_project_root`** / **`canonical_example_project_rel`** 可与上述默认一致，便于代理直接填入 `project_root`。
