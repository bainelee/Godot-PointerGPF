# Task 0 审计：Godot 可执行文件「全盘搜索」相关代码（2026-04-11）

| 路径 | 函数/脚本 | 行为摘要 | 结论 |
|------|-----------|----------|------|
| `mcp/server.py` | `_discover_godot_executable_candidates` | 仅 JSON / 工具参数 / 环境变量 | **留**：无整盘递归 |
| `mcp/server.py` | `_is_godot_editor_running_for_project` | Win32_Process + 命令行匹配 `project_root` | **留**：非文件系统枚举 |
| `tools/game-test-runner/mcp/server_common.py` | `common_windows_godot_candidates` | `ProgramFiles`、`LOCALAPPDATA\Programs` 等根下 `glob("Godot*.exe")` | **留**：固定前缀枚举，非 `D:\` 根递归 |
| 其它 `mcp/`、`tools/`、`scripts/` | — | 用 Cursor `Grep` 检索 `Get-ChildItem`/`where.exe /R` 与 Godot 同现：无命中于 MCP 主路径 | **无删除项** |

**结论（与截图行为）**：`pointer_gpf` 已提交代码中**未发现**对 `C:\`/`D:\` 根目录递归枚举 Godot 的实现；用户截图中的扫盘行为归类为 **IDE 代理即兴 Shell**，由 `godot_executable_resolution` + `docs/gpf-godot-executable-ask-and-persist.md` + `.cursor/rules/gpf-godot-executable-discovery.mdc` 约束正确流程，而非在仓库内「假删」不存在的 Python 扫盘逻辑。
