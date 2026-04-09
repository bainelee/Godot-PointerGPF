# 本地临时目录说明

本文档说明哪些目录属于本地临时目录，不应视为项目正式结构的一部分。

## 目录清单

- `.mcp-backup-*`：更新/修复时生成的本地备份目录。
- `.mcp-update-work-*`：更新流程中的临时工作目录。
- `.worktrees/`：本地 Git 多工作目录容器。
- `examples/godot_minimal/artifacts/`：示例项目本地执行产物。

## 管理原则

- 以上目录默认不纳入发布与结构图。
- 这些目录已通过 `.gitignore` 忽略。
- 需要保留时，仅作为本地排查证据；不建议提交到仓库。

## 清理建议（本地）

在仓库根执行（按需）：

```powershell
Remove-Item -Recurse -Force ".mcp-backup-*"
Remove-Item -Recurse -Force ".mcp-update-work-*"
Remove-Item -Recurse -Force ".worktrees"
Remove-Item -Recurse -Force "examples/godot_minimal/artifacts"
```

执行前请确认目录不包含仍需保留的调试证据。

