# 游戏测试窗口收尾 — 人工验收清单（Windows + Godot 4.6.x）

本清单用于验证「基础测试流程结束后 `(DEBUG)` 游戏测试窗口已结束、Godot 编辑器仍保留」。

## 前置

1. 已配置 Godot 可执行文件（例如 `examples/godot_minimal/tools/game-test-runner/config/godot_executable.json`）。
2. 仓库根目录：`D:/AI/pointer_gpf`（或你的克隆路径）。
3. 目标工程：`examples/godot_minimal`（含 `project.godot`）。

## 步骤

1. 启动 Godot 编辑器并打开 `examples/godot_minimal`，确认**仅一个**编辑器实例加载该工程路径。
2. **不要**手动按 F5；在 PowerShell 中于仓库根执行（避免 `--args` 转义问题）：

```powershell
Set-Location D:\AI\pointer_gpf
python -c "import subprocess,json,sys; j=json.dumps({'failure_handling':'run_only'}); r=subprocess.run([sys.executable,'mcp/server.py','--tool','run_game_basic_test_flow_by_current_state','--project-root','D:/AI/pointer_gpf/examples/godot_minimal','--args',j]); raise SystemExit(r.returncode)"
```

3. 流程结束后（无论成功或失败）：目视确认 **带 `(DEBUG)` 的独立游戏窗口已关闭**；Godot **编辑器**窗口仍存在。
4. 若仍见游戏窗口：收集以下路径内容（或截图）并记入 issue：
   - `examples/godot_minimal/pointer_gpf/tmp/runtime_gate.json`
   - `examples/godot_minimal/pointer_gpf/tmp/teardown_debug_game_last.json`
   - 任务管理器中命令行包含 `godot_minimal` 的 Godot 相关进程列表

## 通过标准

- `(DEBUG)` 游戏测试窗口不可见或已最小化关闭（与编辑器内「停止运行」一致）。
- 编辑器进程未被动退出（除非显式选择了会杀编辑器的 opt-in 参数）。
