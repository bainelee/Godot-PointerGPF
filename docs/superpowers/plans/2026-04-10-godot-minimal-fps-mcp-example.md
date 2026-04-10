# Godot Minimal 示例：UI 场景切分 + FPS 主流程（MCP 测试向）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `examples/godot_minimal` 中现有 UI 拆成独立 `.tscn`，从 `D:\GODOT_Test\ai-godot-test` 原样迁入第一人称射击玩法资源与脚本；运行工程时先进入开始界面，点击「开始游戏」后切换到 3D 关卡场景，使节点路径与场景数量足以支撑 MCP 工具链（打开场景、查节点、执行流程、截图等）的回归与演示。

**Architecture:** 菜单阶段使用单一 `CanvasLayer` 根场景 `main_menu.tscn`，其下以 **PackedScene 实例** 挂载各 UI 子场景，实例节点名保持为 `Dashboard`（可选显示）、`StartScreen`、`UI1`、`UI2Popup`、`UI3`，以尽量保留现有文档/MCP 提示中的路径前缀（如 `UI/UI1`）。3D 阶段使用 `game_level.tscn`（结构对齐源项目的 `main_scene.tscn`），在 `_ready` 中实例化 `fps_controller.tscn` 与 `crosshair.tscn`。场景切换使用 `get_tree().change_scene_to_packed()` 或 `change_scene_to_file()`。

**Tech Stack:** Godot 4.6、GDScript；物理引擎沿用示例工程当前配置（**不强制**安装 Jolt；`CharacterBody3D` 在默认 3D 物理下可运行）。源项目路径：`D:\GODOT_Test\ai-godot-test`。

---

## 文件结构总览（实施前锁定）

| 职责 | 路径 |
|------|------|
| 运行入口（开始界面） | `examples/godot_minimal/scenes/main_menu.tscn`（新建） |
| 3D FPS 关卡 | `examples/godot_minimal/scenes/game_level.tscn`（新建） |
| Figma 风仪表盘布局（原 `UI` 下除开始层/弹窗外的主体静态布局） | `examples/godot_minimal/scenes/ui/ui_dashboard_layout.tscn`（新建） |
| 开始界面（半透明遮罩 + 标题 + 按钮） | `examples/godot_minimal/scenes/ui/ui_start_screen.tscn`（新建） |
| MCP 演示面板 1 / 弹窗 2 / 面板 3 | `examples/godot_minimal/scenes/ui/ui_demo_panel_1.tscn`、`ui_demo_popup_2.tscn`、`ui_demo_panel_3.tscn`（新建） |
| 菜单流程脚本 | `examples/godot_minimal/scripts/main_menu_flow.gd`（新建，由 `main_ui_flow.gd` 改写或替换） |
| 兼容旧文档与 MCP 默认 `scene_file` | `examples/godot_minimal/scenes/main_scene_example.tscn`（**改为**仅实例化 `main_menu.tscn` 或等价组合，见 Task 5） |
| FPS 与玩法（从 ai-godot-test 复制） | `scripts/player/fps_controller.gd`、`scenes/player/fps_controller.tscn`、`scripts/projectiles/bullet.gd`、`scenes/projectiles/bullet.tscn`、`scripts/enemies/test_enemy.gd`、`scenes/enemies/test_enemy.tscn`、`scripts/ui/crosshair.gd`、`scenes/ui/crosshair.tscn`、`shaders/grid.gdshader`、`shaders/grid_material.tres`、`shaders/sprite3d_hit_flash.gdshader`、`shaders/sprite3d_hit_material.tres`、`textures/triangle_inverted_red.png`（及可选 `.import`）、`resources/sprites/enemy_sprite_frames.tres`（可选，敌人场景当前仅用单纹理时可不复制） |
| 关卡逻辑（照搬源 `main_scene.gd`） | `examples/godot_minimal/scripts/game_level.gd`（新建，内容同下 Task 4） |
| 工程入口配置 | `examples/godot_minimal/project.godot`：`run/main_scene` 指向 `res://scenes/main_menu.tscn` |
| MCP 默认场景（与运行入口一致） | `mcp/server.py` 中默认 `scenes/main_scene_example.tscn` → 改为 `scenes/main_menu.tscn` **或** 保留 `main_scene_example.tscn` 为薄包装且仍含 `UI/UI1` 路径（二选一，Task 5 固定方案） |
| 无头截图脚本 | `examples/godot_minimal/scripts/capture_ui_screenshot.gd`：改为加载 `res://scenes/main_menu.tscn`（与主流程一致） |

**复制源根目录（Windows）：** `D:\GODOT_Test\ai-godot-test`

---

### Task 1: 建立 `textures` 与 `shaders` 资源目录并复制依赖文件

**Files:**
- Create: `examples/godot_minimal/textures/triangle_inverted_red.png`（从源复制）
- Create: `examples/godot_minimal/shaders/grid.gdshader`
- Create: `examples/godot_minimal/shaders/grid_material.tres`
- Create: `examples/godot_minimal/shaders/sprite3d_hit_flash.gdshader`
- Create: `examples/godot_minimal/shaders/sprite3d_hit_material.tres`

- [ ] **Step 1: 用 PowerShell 复制二进制与着色器（含 .import 可选）**

```powershell
$src = "D:\GODOT_Test\ai-godot-test"
$dst = "D:\AI\pointer_gpf\examples\godot_minimal"
New-Item -ItemType Directory -Force -Path "$dst\textures","$dst\shaders" | Out-Null
Copy-Item "$src\textures\triangle_inverted_red.png" "$dst\textures\" -Force
Copy-Item "$src\textures\triangle_inverted_red.png.import" "$dst\textures\" -Force -ErrorAction SilentlyContinue
Copy-Item "$src\shaders\grid.gdshader" "$dst\shaders\" -Force
Copy-Item "$src\shaders\grid_material.tres" "$dst\shaders\" -Force
Copy-Item "$src\shaders\sprite3d_hit_flash.gdshader" "$dst\shaders\" -Force
Copy-Item "$src\shaders\sprite3d_hit_material.tres" "$dst\shaders\" -Force
```

- [ ] **Step 2: 在 Godot 编辑器中打开 `examples/godot_minimal` 一次**，让引擎重新导入 `triangle_inverted_red.png`（若未复制 `.import`）。

- [ ] **Step 3: Commit**

```bash
git add examples/godot_minimal/textures examples/godot_minimal/shaders
git commit -m "chore(godot_minimal): add fps shaders and enemy texture from ai-godot-test"
```

---

### Task 2: 复制玩家、子弹、敌人、准星脚本与场景

**Files:**
- Create: `examples/godot_minimal/scripts/player/fps_controller.gd`（与源文件逐行一致）
- Create: `examples/godot_minimal/scenes/player/fps_controller.tscn`
- Create: `examples/godot_minimal/scripts/projectiles/bullet.gd`
- Create: `examples/godot_minimal/scenes/projectiles/bullet.tscn`
- Create: `examples/godot_minimal/scripts/enemies/test_enemy.gd`
- Create: `examples/godot_minimal/scenes/enemies/test_enemy.tscn`
- Create: `examples/godot_minimal/scripts/ui/crosshair.gd`
- Create: `examples/godot_minimal/scenes/ui/crosshair.tscn`

- [ ] **Step 1: 复制 GDScript 与 tscn**

```powershell
$src = "D:\GODOT_Test\ai-godot-test"
$dst = "D:\AI\pointer_gpf\examples\godot_minimal"
foreach ($rel in @(
  "scripts\player\fps_controller.gd",
  "scenes\player\fps_controller.tscn",
  "scripts\projectiles\bullet.gd",
  "scenes\projectiles\bullet.tscn",
  "scripts\enemies\test_enemy.gd",
  "scenes\enemies\test_enemy.tscn",
  "scripts\ui\crosshair.gd",
  "scenes\ui\crosshair.tscn"
)) {
  $s = Join-Path $src $rel
  $d = Join-Path $dst $rel
  New-Item -ItemType Directory -Force -Path (Split-Path $d) | Out-Null
  Copy-Item $s $d -Force
}
```

- [ ] **Step 2: 批量替换 tscn/gd 内资源路径**  
确认上述文件中 **仅** 使用 `res://` 相对路径且前缀仍为 `res://scripts/...`、`res://scenes/...`、`res://shaders/...`、`res://textures/...`；与源一致则**无需改内容**。若 Godot 打开后报 uid 缺失，在编辑器中重新绑定 Script 一次并保存。

- [ ] **Step 3: Commit**

```bash
git add examples/godot_minimal/scripts/player examples/godot_minimal/scenes/player examples/godot_minimal/scripts/projectiles examples/godot_minimal/scenes/projectiles examples/godot_minimal/scripts/enemies examples/godot_minimal/scenes/enemies examples/godot_minimal/scripts/ui examples/godot_minimal/scenes/ui
git commit -m "feat(godot_minimal): import fps player, bullet, enemy, crosshair from ai-godot-test"
```

---

### Task 3: 新建 `game_level.tscn` 与 `game_level.gd`

**Files:**
- Create: `examples/godot_minimal/scripts/game_level.gd`
- Create: `examples/godot_minimal/scenes/game_level.tscn`

- [ ] **Step 1: 写入 `game_level.gd`（与源 `D:\GODOT_Test\ai-godot-test\scripts\main_scene.gd` 一致，仅保证路径为当前工程）**

```gdscript
extends Node3D

## 主场景启动时加载第一人称控制器和准星

func _ready() -> void:
	var fps_scene = load("res://scenes/player/fps_controller.tscn") as PackedScene
	if fps_scene:
		var fps = fps_scene.instantiate()
		fps.position = Vector3(0, 2, 5)
		add_child(fps)

	var crosshair_scene = load("res://scenes/ui/crosshair.tscn") as PackedScene
	if crosshair_scene:
		add_child(crosshair_scene.instantiate())
```

- [ ] **Step 2: 写入 `game_level.tscn`（对应源 `main_scene.tscn`，替换 script 与 enemy 路径为当前工程）**

使用 Godot 编辑器新建 `Node3D` 根节点命名为 `GameLevel`，挂载 `res://scripts/game_level.gd`，添加 `Ground`（`MeshInstance3D` + `PlaneMesh` 20×20）、`GroundCollision`（`StaticBody3D` + `CollisionShape3D` + `BoxShape3D` size `(20, 0.1, 20)`，transform y=-0.05），`Ground` 的 material 指定 `res://shaders/grid_material.tres`，并 **实例化** `res://scenes/enemies/test_enemy.tscn` 子节点，transform 与源一致：`Transform3D(0.6,0,0,0,0.6,0,0,0,0.6, 5, 0, 5)`。

**文本格式参考（若手工合并）：**

```ini
[gd_scene format=3 load_steps=5]

[ext_resource type="Script" path="res://scripts/game_level.gd" id="1_gl"]
[ext_resource type="Material" path="res://shaders/grid_material.tres" id="2_grid_mat"]
[ext_resource type="PackedScene" path="res://scenes/enemies/test_enemy.tscn" id="3_enemy"]

[sub_resource type="PlaneMesh" id="PlaneMesh_ground"]
size = Vector2(20, 20)

[sub_resource type="BoxShape3D" id="BoxShape3D_ground"]
size = Vector3(20, 0.1, 20)

[node name="GameLevel" type="Node3D"]
script = ExtResource("1_gl")

[node name="Ground" type="MeshInstance3D" parent="."]
mesh = SubResource("PlaneMesh_ground")
surface_material_override/0 = ExtResource("2_grid_mat")

[node name="GroundCollision" type="StaticBody3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, -0.05, 0)

[node name="CollisionShape3D" type="CollisionShape3D" parent="GroundCollision"]
shape = SubResource("BoxShape3D_ground")

[node name="TestEnemy" parent="." instance=ExtResource("3_enemy")]
transform = Transform3D(0.6, 0, 0, 0, 0.6, 0, 0, 0, 0.6, 5, 0, 5)
```

- [ ] **Step 3: 运行校验**  
在编辑器中打开 `game_level.tscn`，按 F6 运行当前场景：应出现地面网格、可 WASD 移动、鼠标瞄准、左键射击、敌人面向玩家；ESC 释放鼠标。

- [ ] **Step 4: Commit**

```bash
git add examples/godot_minimal/scripts/game_level.gd examples/godot_minimal/scenes/game_level.tscn
git commit -m "feat(godot_minimal): add fps game_level scene"
```

---

### Task 4: 拆分 UI 子场景（四个 UI 包 + 仪表盘）

**Files:**
- Create: `examples/godot_minimal/scenes/ui/ui_dashboard_layout.tscn`（根节点建议 `Control`，全屏 `anchors_preset = 15`）
- Create: `examples/godot_minimal/scenes/ui/ui_start_screen.tscn`（根节点 `ColorRect`，全屏半透明）
- Create: `examples/godot_minimal/scenes/ui/ui_demo_panel_1.tscn`（根节点 `Panel`，与现 `UI1` 同尺寸）
- Create: `examples/godot_minimal/scenes/ui/ui_demo_popup_2.tscn`（根节点 `Panel`）
- Create: `examples/godot_minimal/scenes/ui/ui_demo_panel_3.tscn`（根节点 `Panel`）

- [ ] **Step 1: 从现有 `main_scene_example.tscn` 剪切节点**  
在编辑器中打开 `examples/godot_minimal/scenes/main_scene_example.tscn`，将下列节点 **原样** 移到对应新场景根下（保留 `offset_*`、`theme_*`、`texture` 引用 `res://assets/figma_image_*.png`）：

| 原父节点 | 原节点名 | 目标场景 | 新场景根类型 |
|----------|----------|----------|----------------|
| `UI` | `Background` … `Text5`（不含 StartScreen、UI1、UI2Popup、UI3） | `ui_dashboard_layout.tscn` | `Control` 命名 `Dashboard` |
| `UI/StartScreen` | 子节点 `StartTitle`、`StartButton` | `ui_start_screen.tscn` | `ColorRect` 命名 `StartScreen`，复制原 StartScreen 的 anchor/color |
| `UI` | `UI1` 整棵 | `ui_demo_panel_1.tscn` | 根命名 `UI1` |
| `UI` | `UI2Popup` 整棵 | `ui_demo_popup_2.tscn` | 根命名 `UI2Popup` |
| `UI` | `UI3` 整棵 | `ui_demo_panel_3.tscn` | 根命名 `UI3` |

- [ ] **Step 2: 在 `ui_start_screen.tscn` 根节点上连接信号**  
将 `StartButton.pressed` 连接到根节点脚本中的 `_on_start_button_pressed`（脚本在 Task 5 统一到 `main_menu_flow.gd` 时也可由父层连接；若子场景自包含信号，使用 `signal start_game_pressed` 由父层 `connect`）。

推荐子场景根脚本 `ui_start_screen.gd`（最小化，仅发信号）：

```gdscript
extends ColorRect

signal start_game_pressed

func _on_start_button_pressed() -> void:
	start_game_pressed.emit()
```

并在编辑器中将 `StartButton.pressed` 连到 `ui_start_screen.gd` 的 `_on_start_button_pressed`。

- [ ] **Step 3: Commit**

```bash
git add examples/godot_minimal/scenes/ui
git commit -m "refactor(godot_minimal): split figma dashboard and demo UI into packed scenes"
```

---

### Task 5: 新建 `main_menu.tscn`、重写流程脚本、薄包装 `main_scene_example.tscn`

**Files:**
- Create: `examples/godot_minimal/scenes/main_menu.tscn`
- Create: `examples/godot_minimal/scripts/main_menu_flow.gd`
- Modify: `examples/godot_minimal/scenes/main_scene_example.tscn`（改为实例化主菜单或保留等价节点树）
- Modify: `examples/godot_minimal/project.godot`（`run/main_scene`）
- Modify: `examples/godot_minimal/scripts/capture_ui_screenshot.gd`
- Modify: `mcp/server.py`（默认 scene 路径，与下文一致）

- [ ] **Step 1: 编写 `main_menu_flow.gd`**

```gdscript
extends CanvasLayer

const GAME_LEVEL := "res://scenes/game_level.tscn"

@onready var dashboard: Control = $Dashboard
@onready var start_screen: Control = $StartScreen
@onready var ui1: Control = $UI1
@onready var ui2_popup: Control = $UI2Popup
@onready var ui3: Control = $UI3


func _ready() -> void:
	dashboard.visible = false
	ui1.visible = false
	ui2_popup.visible = false
	ui3.visible = false
	start_screen.visible = true
	if start_screen.has_signal("start_game_pressed"):
		start_screen.start_game_pressed.connect(_on_start_game)
	# 兼容：若 StartButton 在子场景内由父连接，也可 get_node 连接：
	var btn := start_screen.get_node_or_null("StartButton")
	if btn and btn is BaseButton:
		if not btn.pressed.is_connected(_on_start_game):
			btn.pressed.connect(_on_start_game)


func _on_start_game() -> void:
	get_tree().change_scene_to_file(GAME_LEVEL)


func _on_ui1_open_ui2_button_pressed() -> void:
	ui2_popup.visible = true


func _on_ui2_next_button_pressed() -> void:
	ui2_popup.visible = false
	ui3.visible = true


func _on_ui3_close_button_pressed() -> void:
	ui3.visible = false
```

说明：若 `StartScreen` 使用 Task 4 的 `start_game_pressed` 信号，则 `_ready` 里 `connect` 到 `_on_start_game` 即可，可删除对 `StartButton` 的重复 `pressed` 连接，二者只保留一种。

- [ ] **Step 2: 组装 `main_menu.tscn`**  
根节点 `MainMenu` 类型 `Node3D` 或 `Node`（与旧例一致可用 `Node3D`），子节点 `UI` 类型 `CanvasLayer`，`script = res://scripts/main_menu_flow.gd`。在 `UI` 下以 **实例子场景** 添加，且 **节点名必须为**：

- `Dashboard` ← `ui_dashboard_layout.tscn`
- `StartScreen` ← `ui_start_screen.tscn`
- `UI1` ← `ui_demo_panel_1.tscn`
- `UI2Popup` ← `ui_demo_popup_2.tscn`
- `UI3` ← `ui_demo_panel_3.tscn`

在编辑器中恢复按钮连接（与旧 `main_scene_example.tscn` 相同）：

- `UI/UI1/OpenUI2Button.pressed` → `UI` → `_on_ui1_open_ui2_button_pressed`
- `UI/UI2Popup/NextButton.pressed` → `UI` → `_on_ui2_next_button_pressed`
- `UI/UI3/CloseButton.pressed` → `UI` → `_on_ui3_close_button_pressed`

开始游戏：由 `StartScreen` 信号或 `StartButton` 触发 `_on_start_game`。

- [ ] **Step 3: 将 `main_scene_example.tscn` 改为薄包装（推荐，避免破坏依赖该路径的工具习惯）**

删除原庞大节点树，仅保留：

```ini
[gd_scene format=3 load_steps=2]

[ext_resource type="PackedScene" path="res://scenes/main_menu.tscn" id="1_menu"]

[node name="MainSceneExample" type="Node3D"]

[node name="MainMenu" parent="." instance=ExtResource("1_menu")]
```

注意：包装后 MCP 若使用节点路径 `UI/UI1`，需指向 **实例内部**。Godot 中实例内节点路径为 `MainMenu/UI/UI1`（若 `main_menu` 根为 `Node3D/MainMenu` 且子节点名为 `MainMenu`）。**为保持 `UI/UI1` 路径不变**，更稳妥的包装是：

```ini
[node name="MainSceneExample" type="Node3D"]

[node name="UI" type="CanvasLayer" parent="."]
script = ExtResource("main_menu_flow_script")

[node name="Dashboard" parent="UI" instance=ExtResource("ui_dashboard_layout")]
...
```

即 **不把菜单再套一层 MainMenu**，而是仍在 `MainSceneExample` 下保留 `UI` CanvasLayer 与五个实例子节点。这样 `main_scene_example.tscn` 与 `main_menu.tscn` 会重复。

**推荐最终方案（二选一，实施时只选一种并写进提交说明）：**

- **方案 A（路径最稳）：** `main_menu.tscn` 的根为 `CanvasLayer` 名 `UI`，脚本挂在 `UI` 上；`main_scene_example.tscn` 仅包含 `[node name="MainSceneExample" type="Node3D"]` + `instance` 子节点 `MainMenu` 指向 `main_menu.tscn`，则运行时路径为 `MainMenu/Dashboard`… **不是** `UI/UI1`。需在 Task 6 把 MCP 默认路径改为 `/root/MainMenu/UI1` 或统一用 `main_scene_example` 内重复挂载 `UI`（方案 B）。

- **方案 B（与旧 MCP 提示一致）：** 删除独立 `main_menu.tscn` 作为运行场景，**直接**以 `main_scene_example.tscn` 为运行入口：根 `Node3D`，子节点 `UI`（CanvasLayer + `main_menu_flow.gd`），下挂五个 `instance`。`project.godot` 的 `run/main_scene` 仍指向 `main_scene_example.tscn`（更新 uid）。`capture_ui_screenshot.gd` 仍加载 `main_scene_example.tscn`。**不修改** `mcp/server.py` 默认路径。  
若采用方案 B，Task 5 中「新建 `main_menu.tscn`」改为可选，或 `main_menu.tscn` 仅作可被其它工程引用的重复文件。

**本计划默认采用方案 B**（最少改动 MCP 与测试期望路径 `UI/...`）。

- [ ] **Step 4: 按方案 B 更新 `project.godot`**

```ini
[application]
run/main_scene="res://scenes/main_scene_example.tscn"
```

保存后若 uid 变化，用编辑器重新保存场景以刷新 uid。

- [ ] **Step 5: `capture_ui_screenshot.gd` 保持** `load("res://scenes/main_scene_example.tscn")` **不变**（方案 B）。

- [ ] **Step 6: Commit**

```bash
git add examples/godot_minimal/scenes/main_scene_example.tscn examples/godot_minimal/scripts/main_menu_flow.gd examples/godot_minimal/project.godot
git commit -m "feat(godot_minimal): menu flow to fps level; compose UI from packed scenes"
```

---

### Task 6: 若采用方案 A，同步 MCP 默认场景与节点路径文档

**Files:**
- Modify: `mcp/server.py`（约 2932、2941 行默认 `scenes/main_menu.tscn`）
- Modify: 本仓库内引用 `node_visible:UI/UI1` 的说明（若路径变更）

- [ ] **Step 1: 仅在方案 A 下修改 `mcp/server.py`**

将默认参数从 `"scenes/main_scene_example.tscn"` 改为 `"scenes/main_menu.tscn"`（或保持 `main_scene_example.tscn` 为包装并更新文档中的节点路径为完整 `MainMenu/UI/UI1`）。

- [ ] **Step 2: Commit**

```bash
git add mcp/server.py
git commit -m "fix(mcp): align default godot_minimal scene with new entry scene"
```

---

### Task 7: Python 测试 — 断言新场景与入口存在

**Files:**
- Create: `tests/test_godot_minimal_fps_example_layout.py`

- [ ] **Step 1: 添加测试文件**

```python
from __future__ import annotations

import unittest
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


class GodotMinimalFpsExampleTests(unittest.TestCase):
    def test_fps_scenes_and_scripts_exist(self) -> None:
        root = _repo_root() / "examples" / "godot_minimal"
        must_exist = [
            root / "scenes" / "game_level.tscn",
            root / "scenes" / "player" / "fps_controller.tscn",
            root / "scenes" / "enemies" / "test_enemy.tscn",
            root / "scenes" / "projectiles" / "bullet.tscn",
            root / "scenes" / "ui" / "crosshair.tscn",
            root / "scripts" / "game_level.gd",
            root / "scripts" / "player" / "fps_controller.gd",
            root / "textures" / "triangle_inverted_red.png",
            root / "shaders" / "grid.gdshader",
        ]
        for p in must_exist:
            self.assertTrue(p.is_file(), msg=f"missing {p.relative_to(root)}")

    def test_main_scene_example_lists_ui_instances(self) -> None:
        """主场景应仍包含 UI1 等关键字，便于 MCP/文档节点路径（方案 B）。"""
        scene = _repo_root() / "examples" / "godot_minimal" / "scenes" / "main_scene_example.tscn"
        text = scene.read_text(encoding="utf-8")
        self.assertIn("UI1", text)
        self.assertIn("StartScreen", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试**

```bash
cd D:\AI\pointer_gpf
python -m pytest tests/test_godot_minimal_fps_example_layout.py -v
```

Expected: 全部 PASSED。

- [ ] **Step 3: Commit**

```bash
git add tests/test_godot_minimal_fps_example_layout.py
git commit -m "test: assert godot_minimal fps example files exist"
```

---

### Task 8: 手工验收清单（MCP 与玩法）

- [ ] **Step 1: 运行工程**  
Godot 打开 `examples/godot_minimal`，F5：应只看到开始界面（仪表盘默认隐藏）；点击「Start Game」进入 3D 场景。

- [ ] **Step 2: 玩法**  
WASD、Shift、Space、鼠标、左键射击、ESC 切鼠标；敌人可见且命中时有受击反馈。

- [ ] **Step 3: MCP 向**  
确认至少存在以下可独立打开的场景文件：`ui_dashboard_layout.tscn`、`ui_start_screen.tscn`、`ui_demo_panel_1.tscn`、`game_level.tscn`、`fps_controller.tscn`。在方案 B 下主场景中仍存在节点路径 `UI/UI1` 供 `node_visible` 类工具演示。

- [ ] **Step 4: Commit**（仅当有文档或小修正时）

```bash
git commit --allow-empty -m "chore: verify godot_minimal fps menu flow manually"
```

---

## 自审摘要

1. **Spec 覆盖：** UI 切分（Task 4–5）、FPS 照搬（Task 1–3）、主流程开始→3D（Task 5）、MCP 测试向文件与路径（Task 6–8）均已覆盖。  
2. **占位符：** 已避免 TBD；方案 A/B 在 Task 5 明确二选一及后果。  
3. **类型与路径：** `game_level.gd` 与源 `main_scene.gd` 一致；`test_enemy.tscn` 纹理路径为 `res://textures/triangle_inverted_red.png`，与 Task 1 目录一致。

**缺口说明：** 源工程 `project.godot` 含 Jolt 与 d3d12 驱动项；本计划刻意不写入，以免未安装 Jolt 的编辑器报错。若需与源完全一致，可在 `project.godot` 增加 `[physics]\n3d/physics_engine="Jolt Physics"`（需本地已启用该模块）。

---

**计划已保存至 `docs/superpowers/plans/2026-04-10-godot-minimal-fps-mcp-example.md`。两种执行方式：**

**1. Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间人工快速审阅，迭代快。  
**2. Inline Execution** — 本会话内按 `executing-plans` 批量执行并设检查点。

**你希望采用哪一种？**
