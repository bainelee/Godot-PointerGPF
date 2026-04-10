# Basic Flow Bridge Stall Followup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 `examples/godot_minimal` 上 `run_game_basic_test_flow_by_current_state` 中由桥接点击与切场景竞态、以及资源路径错误导致的 `ENGINE_RUNTIME_STALLED` / `enter_game` 恒失败，使流程在业务失败以外可稳定跑通。

**Architecture:** 在 `runtime_bridge.gd` 的 `_perform_click` 中，在可能触发 `change_scene_to_file` 的 `pressed` 信号之前，先缓存诊断用 `node_path` 与虚拟点击用的屏幕坐标；信号之后不再对已可能释放的 `Control` 调用 `get_path()` / `get_global_rect()`。游戏侧核对 `game_level.gd` 中 `preload`/`load` 与磁盘路径一致。验证通过 Python CLI 同步跑一次基础流程并检查 `project_close.acknowledged` 与编辑器进程仍存活。

**Tech Stack:** Godot 4.x GDScript、仓库内 MCP（`mcp/server.py`）、pytest（插件侧若有单测扩展）、Windows PowerShell。

---

## 文件结构（将创建或修改）

| 文件 | 职责 |
|------|------|
| `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd` | 桥接点击与诊断路径的权威实现；改 `_perform_click` 时序 |
| `examples/godot_minimal/addons/pointer_gpf/runtime_bridge.gd` | 与模板同步的副本，必须同 diff |
| `examples/godot_minimal/scripts/game_level.gd` | 主关卡子场景与 HUD 的加载链 |
| `examples/godot_minimal/scenes/ui/game_pointer_hud.tscn` | HUD 场景资源（路径需与 preload 一致） |
| `examples/godot_minimal/scenes/player/fps_controller.tscn` | 第一人称场景（与 `load` 路径一致） |
| `tests/test_runtime_gate_marker_plugin.py` 或新建 `tests/test_runtime_bridge_click.py` | 若可对纯 GDScript 逻辑做文档化契约测试则加；否则以集成 CLI 为主 |

---

### Task 1: 修复 `_perform_click` 与切场景的竞态（模板 + 示例同步）

**Files:**
- Modify: `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd`（`_perform_click` 函数体）
- Modify: `examples/godot_minimal/addons/pointer_gpf/runtime_bridge.gd`（同上）

- [ ] **Step 1: 写出期望行为（手工验收标准）**

在点击会触发 `get_tree().change_scene_to_file(...)` 的按钮后，桥接不得再对已释放节点调用 `get_path()`；不得于 `emit` 之后对同一 `Control` 调用 `get_global_rect()`。

- [ ] **Step 2: 修改 `_perform_click`（BaseButton 分支）**

将 `BaseButton` 分支改为：先若 `btn.is_inside_tree()` 则 `var reported_path := str(btn.get_path())`，否则 `reported_path := ""`；再 `var click_pos := _control_center(btn)`；再 `pressed.emit()` / `emit_signal("pressed")`；再 `_dispatch_click_virtual(click_pos)`；最后 `return {"ok": true, "node_path": reported_path}`。

参考实现（整段替换原 `if node is BaseButton:` 块内语句顺序与变量）：

```gdscript
        if node is BaseButton:
            var btn := node as BaseButton
            var reported_path := ""
            if btn.is_inside_tree():
                reported_path = str(btn.get_path())
            var click_pos := _control_center(btn)
            if btn.has_signal("pressed"):
                btn.pressed.emit()
            btn.emit_signal("pressed")
            _dispatch_click_virtual(click_pos)
            return {"ok": true, "node_path": reported_path}
```

- [ ] **Step 3: 修改 `_perform_click`（Control 分支）**

对 `Control` 分支同样先缓存 `reported_path` 与 `click_pos`，再 `_dispatch_click_virtual`，避免 `emit` 后 `get_path()`：

```gdscript
        if node is Control:
            var ctrl := node as Control
            var reported_path_c := ""
            if ctrl.is_inside_tree():
                reported_path_c = str(ctrl.get_path())
            var click_pos_c := _control_center(ctrl)
            _dispatch_click_virtual(click_pos_c)
            return {"ok": true, "node_path": reported_path_c}
```

（若该分支未来会连接会切场景的信号，顺序已与 Button 一致。）

- [ ] **Step 4: 兜底分支**

对最后的 `_dispatch_click_virtual(fallback_pos)` 后 `str(node.get_path())`：若 `node` 可能因侧效应脱离树，改为在 dispatch 前缓存路径（与上同理），或仅在 `node.is_inside_tree()` 时填路径。

- [ ] **Step 5: 同步两份文件并提交**

```bash
git add godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd examples/godot_minimal/addons/pointer_gpf/runtime_bridge.gd
git commit -m "fix(runtime_bridge): cache path and click pos before signals that may change scene"
```

---

### Task 2: 核对 `game_level.gd` 资源链与磁盘一致

**Files:**
- Read: `examples/godot_minimal/scripts/game_level.gd`
- Verify exist: `examples/godot_minimal/scenes/ui/game_pointer_hud.tscn`
- Verify exist: `examples/godot_minimal/scenes/player/fps_controller.tscn`
- Verify exist: `examples/godot_minimal/scenes/ui/crosshair.tscn`

- [ ] **Step 1: 列出 `game_level.gd` 中所有 `preload`/`load` 路径**

当前文件引用：

- `const POINTER_HUD := preload("res://scenes/ui/game_pointer_hud.tscn")`
- `load("res://scenes/player/fps_controller.tscn")`
- `load("res://scenes/ui/crosshair.tscn")`

- [ ] **Step 2: 若任一路径缺失或大小写不一致，修正 `.gd` 或重命名资源文件**

使 Godot 资源导入器可解析（Windows 上路径大小写不敏感但 Git 与导出可能敏感）。

- [ ] **Step 3: 在编辑器中打开 `game_level.tscn` 一次确认无加载错误（可选）**

若无法开编辑器，至少用仓库内文件存在性 + 后续 CLI 流程验证。

- [ ] **Step 4: 提交（仅当确有路径修正时）**

```bash
git add examples/godot_minimal/scripts/game_level.gd
git commit -m "fix(game_level): align scene paths with on-disk assets"
```

---

### Task 3: 运行基础测试流程并记录证据

**Files:**
- 证据：`examples/godot_minimal/pointer_gpf/gpf-exp/runtime/flow_run_report_*.json`
- 证据：`pointer_gpf/tmp/runtime_diagnostics.json`（若生成）

- [ ] **Step 1: 在项目根执行（同步等待结束）**

```powershell
cd D:\AI\pointer_gpf
python mcp\server.py --tool run_game_basic_test_flow_by_current_state --project-root "D:\AI\pointer_gpf\examples\godot_minimal" --args "{}"
```

- [ ] **Step 2: 期望结果**

- 返回 JSON 中不应再出现因 `get_path` / 非树节点导致的桥接异常链（若 MCP 将其归类为 `ENGINE_RUNTIME_STALLED`，应消失或显著减少）。
- 若配置了 `close_project_on_finish`，检查 `project_close.acknowledged` 为真且编辑器进程仍存在（与仓库规则「停 Play、不关编辑器」一致）。

- [ ] **Step 3: 失败时**

读取 `pointer_gpf/tmp/runtime_diagnostics.json` 与最新 `flow_run_report_*.json`，记录 `blocking_point`（具体步骤名 + 错误摘要）与 `next_actions`（下一处代码修改点）。

---

## Self-Review

1. **Spec coverage:** 上游摘要中的三点（`_perform_click` 竞态、`game_level` 资源、`runtime_gate` 语义）中，前两点由 Task 1–2 覆盖；`runtime_gate` 为文档/沟通澄清，无代码任务（已在摘要中说明）。
2. **Placeholder scan:** 无 TBD。
3. **Type consistency:** 返回值仍为 `Dictionary`，键 `ok` / `node_path` / `message` 与现有调用方一致。

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-11-basic-flow-bridge-stall-followup.md`. Two execution options:**

**1. Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间复核，迭代快。

**2. Inline Execution** — 本会话内用 executing-plans 批量执行并设检查点。

**Which approach?**
