# Gameplayflow Fix Loop 操作说明

## 何时启用

- `run_game_flow` 返回非零或 `status` 非 `passed`，且希望按回合记录失败原因与重试边界时使用 `bounded_auto_fix`（见工具参数说明）。

## 状态文件

- 运行目录下 `fix_loop_state.json`：`fix_loop.rounds`、`rounds_executed`、`max_rounds`、`status`（如 `resolved` / `exhausted`）。

## 恢复执行

- **`resume_fix_loop`**：传入 `run_id`、`project_root`，可选 `artifact_base` 指向自定义 `artifacts/test-runs` 根。

## 验收

- 终端成功路径：返回 `ok: true` 且 `result.fix_loop.rounds` 为非空列表。
- 耗尽路径：`status == exhausted` 时仍应携带完整 `rounds` 便于审计。

## 与 stepwise / chat 关系

- Fix loop 针对 **整段 flow 运行** 的自动修复回合；stepwise 为 **单步推进**。二者可并行存在于不同 `run_id`，注意 `runtime_lock` 与「同项目单会话」策略。
