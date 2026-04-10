# GPF × AI 代理 / IDE 集成契约

本文说明：**终端用户**、**自动化代理（含 AI IDE）** 与 **CI** 在使用 PointerGPF（GPF）跑基础测试流程时的责任边界。目标：用户完成「安装与初始化」后，**不因 CI 环境变量或遗漏字段**而被迫手动按 Play 或改 shell 才能走自动修复。

> **给终端用户：** 你不需要记住任何环境变量名。用自然语言说「跑一遍基础测试流程」时，助手应先给你一个 **二选一** 的澄清问题（固定文案见 **`docs/gpf-nl-basic-flow-clarifying-questions.md`**）。下面「环境变量」小节主要给 **CI 与脚本集成方** 阅读。

## 1. 用户一次性义务（类比「插电」）

用户或工程维护者需保证：

- 已在目标 Godot 工程中 **安装并启用** GPF 插件（`addons/` + `project.godot` 插件段）。
- 已执行 **`init_project_context`** 或 **`refresh_project_context`**，上下文目录可用。
- 调用工具时传入 **正确且非临时禁行** 的 **`project_root`**（临时目录仍受仓库既有安全策略约束）。
- 本机存在 **可发现的 Godot 编辑器**（或按文档配置 `godot_executable` / 项目内 `tools/game-test-runner/config/godot_executable.json`）。

以上不满足时，返回体中的 **`blocking_point`**、`engine_bootstrap`、`next_actions` 为**硬失败依据**，不是「请用户去按 F5」的软性提示。

## 2.（集成方）代理如何覆盖 CI 的关自动修

终端用户侧请优先走 **`docs/gpf-nl-basic-flow-clarifying-questions.md`**（AskQuestion 二选一后再调 MCP），不要在对话里向用户口述本节环境变量名。

当代理代表用户执行 **`run_game_basic_test_flow`** 或 **`run_game_basic_test_flow_by_current_state`** 且 **未显式传** `auto_repair` 时，集成方可二选一（推荐两者同时满足）：

1. **环境变量**：在运行 `python mcp/server.py` 的进程中设置 **`GPF_AGENT_SESSION_DEFAULTS=1`**（或 `true` / `yes`，大小写不敏感，见 `mcp/server.py` 中 `_truthy_env`）。
2. **请求 JSON**：传入 **`"agent_session_defaults": true`**。

效果：**即使** shell 继承了 CI 的 **`GPF_AUTO_REPAIR_DEFAULT=0`**，仍默认 **`auto_repair: true`**（外层修复环开启）。

**显式**传入 **`"auto_repair": false`** 时 **始终关闭** 自动修复，不受代理会话标志影响（用于用户明确要「只跑不修」）。

## 3. CI 义务（不要冒充代理会话）

- **不得** 在 GitHub Actions / 批处理脚本中设置 **`GPF_AGENT_SESSION_DEFAULTS`**。
- 可继续设置 **`GPF_AUTO_REPAIR_DEFAULT=0`** 以降低 CI 成本与副作用；此时 **未** 声明代理会话的本地/用户调用仍默认关闭自动修复，符合预期。

## 4. play_mode 门禁与等待

- GPF 在 **`_ensure_runtime_play_mode`** 中负责：请求进入 Play、在可自动拉起时拉起编辑器等；详见返回中的 **`engine_bootstrap`**。
- 当声明了代理会话（环境或参数）时，对 gate 的 **等待时间下限** 会略高于非代理路径，以减少「编辑器已开但尚未写入 gate」的竞态误杀（实现见 `mcp/server.py`）。

## 5. 与用户文档的关系

- 面向步骤与命令的 **`docs/quickstart.md`**、**`docs/mcp-basic-test-flow-reference-usage.md`**：保留用户侧说明，并 **链接到本文** 供「代理/集成方」阅读。
- 自然语言跑流程前的 **AskQuestion 固定文案**：**`docs/gpf-nl-basic-flow-clarifying-questions.md`**。
- 本文 **不** 要求终端用户理解 `GPF_AGENT_SESSION_DEFAULTS`；该变量由 **IDE 集成、Cursor 规则、或代理包装脚本** 注入即可。

## 6. 字段对照

| 机制 | 类型 | 说明 |
|------|------|------|
| `GPF_AUTO_REPAIR_DEFAULT` | 环境 | `0`/`false` 时，在未传 `auto_repair` 且 **未** 声明代理会话的情况下，默认关闭外层自动修复（CI 常用）。 |
| `GPF_AGENT_SESSION_DEFAULTS` | 环境 | 为真时，在未传 `auto_repair` 时 **强制** 默认开启 `auto_repair`（压过上一行）。 |
| `agent_session_defaults` | 工具参数 | 与上一行等效，单次请求级。 |
| `failure_handling` | 工具参数 | `run_only` / `auto_try_fix`，与用户 AskQuestion 选项一一对应；见 **`docs/design/99-tools/17-basic-flow-failure-handling-contract.md`**。 |
