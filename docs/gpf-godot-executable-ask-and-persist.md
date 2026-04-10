# Godot 可执行文件：询问用户并持久化

## 何时必须询问用户

当 `run_game_basic_test_flow` / `run_game_basic_test_flow_by_current_state` 返回失败，且 `error.details.engine_bootstrap.launch_error` 为 **`no_executable_candidates`**，或 `error.details.godot_executable_resolution.status` 为 **`missing`** 时，代理**必须先**用 AskQuestion 向用户索取 **Godot 4.x 编辑器** 的 **`Godot*.exe` 绝对路径**（Windows 示例：`D:\Godot\Godot_v4.2.2-stable_win64.exe`）。**不要**自行编写对 `C:\`/`D:\` 根目录递归、`where.exe /R` 等「扫盘式」Shell 来「找 Godot」——那是错误流程；若仓库内仍有脚本这么做，应在代码层删除（见 `docs/superpowers/plans/2026-04-11-godot-path-ask-persist-no-full-disk-search.md` 的 Task 0）。

也可调用 MCP 工具 **`configure_godot_executable`**（传入 `project_root` 与 `godot_executable`）由服务端校验路径并写入 JSON。

## 持久化路径（按 project_root）

- 相对路径：`tools/game-test-runner/config/godot_executable.json`
- 绝对路径：`{project_root}/tools/game-test-runner/config/godot_executable.json`
- 目录不存在时：创建 `tools/game-test-runner/config` 目录。

## JSON 文件内容（UTF-8）

```json
{
  "godot_executable": "D:/Godot/Godot_v4.2.2-stable_win64.exe"
}
```

键名允许使用 **`godot_executable`**（推荐）、`godot_bin` 或 `GODOT_BIN` 之一；与 `tools/game-test-runner/core/godot_executable_config.py` 一致。

## 用户已在消息中给出路径时

若用户在同一条消息中已给出可验证的绝对路径且以 `.exe` 结尾（Windows），可跳过 AskQuestion，但仍须在写入 JSON 后**复述**已采用的路径与文件位置。

## 写入后

重新执行同一 `project_root` 下的 `run_game_basic_test_flow*`（可在 `--args` 中继续传 `failure_handling` 等字段）。

## 正确排障顺序（与仓库 `AGENTS.md` 永久工程原则一致）

1. 读 MCP 返回的 `godot_executable_resolution.persist_abs` 与 `example_object`。
2. AskQuestion → 用户确认路径 → 写入该 JSON（或调用 `configure_godot_executable`）。
3. 重跑同一 `project_root` 的流程。
4. 若仍失败：查 `engine_bootstrap` 其它字段，**不要**扩大搜索范围到整盘。
