# 基础测试流程：失败处理契约（`failure_handling`）

## 问题（工程设计）

仅依赖 **AskQuestion** 等 IDE 交互，无法被 **CLI、CI、无头 agent** 强制执行；代理也可能跳过提问直接调工具，导致用户意图与 `auto_repair` 行为不一致。

## 解决（契约层）

在 **`run_game_basic_test_flow`** 与 **`run_game_basic_test_flow_by_current_state`** 的入参中增加可选字段 **`failure_handling`**，取值为：

| 值 | 含义（与用户可见文案对齐） | 在未传 `auto_repair` 时的效果 |
|----|---------------------------|------------------------------|
| `run_only` | 只跑验证，失败时不要自动改工程 | `auto_repair` 视为 **关闭** |
| `auto_try_fix` | 失败时自动尝试修复并重试 | `auto_repair` 视为 **开启**（与 `agent_session_defaults: true` 同强度，可压过 `GPF_AUTO_REPAIR_DEFAULT=0`） |

**优先级：** 若调用方显式传入 **`auto_repair`**，则以 **`auto_repair`** 为准（`failure_handling` 不参与）。

**省略 `failure_handling`：** 保持既有逻辑：`agent_session_defaults` / `GPF_AGENT_SESSION_DEFAULTS` → `GPF_AUTO_REPAIR_DEFAULT`。

**非法值：** 非空且不是 `run_only` / `auto_try_fix` → **`INVALID_ARGUMENT`**（可机器校验，便于集成测试）。

## 与 AskQuestion 的关系

- **AskQuestion** 仍是面向人类的 **UX**；用户选项 **`auto_try_fix` / `run_only`** 应 **原样映射** 为 JSON **`failure_handling`** 字段，代理不必再拼 `agent_session_defaults` + 省略 `auto_repair` 的组合。
- **脚本 / CI** 直接传 **`failure_handling`**，无需 AskQuestion。

## 实现位置

- `mcp/server.py`：` _parse_auto_repair_params`
- 工具 schema：`failure_handling` 的 `enum` 与说明
