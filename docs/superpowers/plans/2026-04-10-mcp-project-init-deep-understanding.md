# MCP 项目初始化深度理解（场景排布 / 可点性 / 玩法语义）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `init_project_context` / `refresh_project_context` 生成的依据文档与 `index.json` 中，超越「枚举 UI 与按钮」层面，补充**场景树排布、静态可交互性推断、玩家可操作集合、游戏类型与同类典型操作对照**，使 MCP 对目标项目的理解更接近「玩家与自动化实际能做什么」，并显式标出静态分析的局限。

**Architecture:** 在 `mcp/operational_profile.py` 旁新增专注解析与推断的模块（例如 `mcp/scene_interaction_model.py`），对 `.tscn` 做**结构化节点解析**（父子、类型、Control 几何、`visible` / `mouse_filter` / `modulate` / `z_index`），在**假定根视口尺寸**（来自 `project.godot` 的 `window/size` 或默认 1920×1080）下计算**近似屏幕矩形**与**祖先可见性**；将结果与现有 `operational_profile` 的阶段划分合并，生成扩展 Markdown（可并入 `06` 或新增 `07`，见 Task 5）与 `index.json` 字段。另增**小型静态「类型—典型操作」知识表**（Python 常量或 JSON，无外部网络），由**脚本信号 + 场景根类型 + InputMap** 触发「本项目可能具备的玩法动词」与「同类游戏通常具备」的对照段落。`design_game_basic_test_flow` 仅消费带 **`interaction_likelihood`** 或 **`automation_notes`** 标签的候选，降低「存在节点但玩家永远点不到」的误报权重。

**Tech Stack:** Python 3.11+、正则与轻量解析（不引入 Godot 头less）、现有 `mcp/server.py` 上下文管线、Godot 4.x `.tscn` 文本格式。

---

## 文件结构（落地前锁定）

| 文件 | 职责 |
|------|------|
| `mcp/scene_interaction_model.py`（新建） | 解析 `.tscn` 节点块；构建节点表；Control 近似 AABB；祖先可见性；`mouse_filter`；静态「是否可能被同层遮挡」的简化规则 |
| `mcp/gameplay_archetype_hints.py`（新建） | genre 关键词与「典型操作→效果」只读表；与项目信号求交生成 `has / unknown / absent` |
| `mcp/operational_profile.py`（修改） | 调用上述模块；把 `ui_interaction_summary`、`gameplay_understanding` 并入 bundle 的 `data` 与 Markdown |
| `mcp/server.py`（修改） | `_derive_flow_candidates` 或后置过滤：为候选附加 `static_interaction` 元数据；可选降低 `hidden_occluded` 的排序权重 |
| `tests/test_scene_interaction_model.py`（新建） | 针对隐藏按钮、IGNORE 鼠标、全屏遮罩下子控件的用例 |
| `tests/test_gameplay_archetype_hints.py`（新建） | 表格与求交逻辑快照测试 |
| `tests/test_operational_profile.py`（修改） | 断言新章节或新字段存在 |

---

### Task 1: `.tscn` 节点块解析与节点表

**Files:**
- Create: `mcp/scene_interaction_model.py`
- Test: `tests/test_scene_interaction_model.py`

- [ ] **Step 1: 编写失败用例（解析单场景内两个 Control 的 parent 与 name）**

```python
# tests/test_scene_interaction_model.py
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
MCP = REPO / "mcp"
if str(MCP) not in sys.path:
    sys.path.insert(0, str(MCP))

def test_parse_ui_start_screen_has_start_button_under_start_screen():
    from scene_interaction_model import parse_tscn_nodes

    root = REPO / "examples/godot_minimal"
    text = (root / "scenes/ui/ui_start_screen.tscn").read_text(encoding="utf-8")
    nodes = parse_tscn_nodes(text)
    by_name = {n.name: n for n in nodes}
    assert "StartScreen" in by_name and "StartButton" in by_name
    assert by_name["StartButton"].parent_path == "."
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_scene_interaction_model.TestParseTscnNodes.test_parse_ui_start_screen_has_start_button_under_start_screen -v`

Expected: `ImportError` 或 `AttributeError`（模块未实现）

- [ ] **Step 3: 实现最小 `parse_tscn_nodes`**

在 `mcp/scene_interaction_model.py` 中：

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedNode:
    name: str
    type_name: str
    parent_path: str  # "." 或 "StartScreen" 或 "UI/Panel"
    raw_attrs: dict[str, str] = field(default_factory=dict)


_NODE_HEADER = re.compile(
    r'^\[node\s+name="([^"]+)"\s+type="([^"]+)"(?:\s+parent="([^"]*)")?\]'
)


def parse_tscn_nodes(tscn_text: str) -> list[ParsedNode]:
    nodes: list[ParsedNode] = []
    current: ParsedNode | None = None
    for line in tscn_text.splitlines():
        m = _NODE_HEADER.match(line.strip())
        if m:
            name, typ, parent = m.group(1), m.group(2), m.group(3)
            parent_path = "." if parent is None else parent.strip()
            current = ParsedNode(name=name, type_name=typ, parent_path=parent_path, raw_attrs={})
            nodes.append(current)
            continue
        if current is None:
            continue
        if "=" in line and not line.strip().startswith(";"):
            key, _, val = line.partition("=")
            current.raw_attrs[key.strip()] = val.strip()
    return nodes
```

- [ ] **Step 4: 运行测试通过**

Run: `python -m unittest tests.test_scene_interaction_model.TestParseTscnNodes.test_parse_ui_start_screen_has_start_button_under_start_screen -v`

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add mcp/scene_interaction_model.py tests/test_scene_interaction_model.py
git commit -m "feat(mcp): parse Godot tscn node headers into ParsedNode list"
```

---

### Task 2: Control 近似矩形与视口内判定

**Files:**
- Modify: `mcp/scene_interaction_model.py`
- Modify: `tests/test_scene_interaction_model.py`

- [ ] **Step 1: 失败测试（StartButton 在 1920×1080 内）**

```python
def test_start_button_approx_rect_inside_viewport():
    from scene_interaction_model import parse_tscn_nodes, control_screen_rect, read_viewport_size_from_project

    root = REPO / "examples/godot_minimal"
    text = (root / "scenes/ui/ui_start_screen.tscn").read_text(encoding="utf-8")
    nodes = {n.name: n for n in parse_tscn_nodes(text)}
    vw, vh = read_viewport_size_from_project(root / "project.godot")
    rect = control_screen_rect(nodes, "StartButton", viewport=(vw, vh))
    assert rect is not None
    x, y, w, h = rect
    assert w > 0 and h > 0
    assert 0 <= x <= vw and 0 <= y <= vh and x + w <= vw + 1 and y + h <= vh + 1
```

- [ ] **Step 2: 实现 `read_viewport_size_from_project` 与简化 `control_screen_rect`**

在 `scene_interaction_model.py` 追加（仅支持 `layout_mode = 0` + `offset_*` 的常见 UI；根父为 `.` 时直接使用 offset）：

```python
import re
from pathlib import Path


def read_viewport_size_from_project(project_godot: Path, default: tuple[int, int] = (1920, 1080)) -> tuple[int, int]:
    raw = project_godot.read_text(encoding="utf-8", errors="replace")
    mw = re.search(r"window/size/viewport_width\s*=\s*(\d+)", raw)
    mh = re.search(r"window/size/viewport_height\s*=\s*(\d+)", raw)
    if mw and mh:
        return int(mw.group(1)), int(mh.group(1))
    return default


def _float_attr(node: ParsedNode, key: str, default: float = 0.0) -> float:
    v = node.raw_attrs.get(key, "")
    try:
        return float(v.split("(", 1)[-1].split(")", 1)[0].strip() or default)
    except ValueError:
        return default


def control_screen_rect(
    nodes_by_name: dict[str, ParsedNode],
    control_name: str,
    *,
    viewport: tuple[int, int],
) -> tuple[float, float, float, float] | None:
    n = nodes_by_name.get(control_name)
    if not n or "Button" not in n.type_name and "Control" not in n.type_name:
        return None
    # 最小版：仅 offset_left/top/right/bottom 定义固定矩形（Godot 控件常用）
    l = _float_attr(n, "offset_left")
    t = _float_attr(n, "offset_top")
    r = _float_attr(n, "offset_right")
    b = _float_attr(n, "offset_bottom")
    if r <= l or b <= t:
        return None
    return (l, t, r - l, b - t)
```

- [ ] **Step 3: 运行测试**

Run: `python -m unittest tests.test_scene_interaction_model -v`

Expected: 全部 `ok`

- [ ] **Step 4: Commit**

```bash
git add mcp/scene_interaction_model.py tests/test_scene_interaction_model.py
git commit -m "feat(mcp): viewport size and simple Control rect from offsets"
```

---

### Task 3: 静态「不可点 / 被遮挡」启发式

**Files:**
- Modify: `mcp/scene_interaction_model.py`
- Modify: `tests/test_scene_interaction_model.py`

- [ ] **Step 1: 失败测试（visible = false 的祖先导致子按钮 unlikely）**

在 `examples/godot_minimal` 的临时副本或内联最小 tscn 字符串构造：

```python
MINIMAL_HIDDEN = '''
[gd_scene format=3]
[node name="Root" type="Control"]
visible = false
[node name="Btn" type="Button" parent="."]
offset_right = 100.0
offset_bottom = 40.0
'''

def test_button_under_invisible_ancestor_flagged():
    from scene_interaction_model import parse_tscn_nodes, summarize_control_interaction

    nodes = parse_tscn_nodes(MINIMAL_HIDDEN)
    by = {n.name: n for n in nodes}
    s = summarize_control_interaction(by, "Btn", viewport=(1920, 1080))
    assert s["ancestor_visible"] is False
    assert s["player_click_likelihood"] in ("low", "none")
```

- [ ] **Step 2: 实现 `summarize_control_interaction`**

规则（写死在代码里，文档中说明）：

- 沿 `parent_path` 向上解析可见性：任一祖先节点块若 `visible = false` → `ancestor_visible=False`
- `mouse_filter = 2`（Godot MOUSE_FILTER_IGNORE）→ `receives_mouse=False`
- `modulate = Color(..., a)` 若可解析且 alpha 为 0 → `effectively_invisible=True`
- `player_click_likelihood`: `none` 若祖先不可见或 IGNORE；`low` 若矩形与视口不相交或面积 0；否则 `medium`（未实现全屏叠层 Z 序精确遮挡时不上调为 `high`）

```python
def _ancestor_chain(nodes_by_name: dict[str, ParsedNode], control_name: str) -> list[ParsedNode]:
    out: list[ParsedNode] = []
    cur = nodes_by_name.get(control_name)
    if not cur:
        return out
    safety = 0
    while cur is not None and safety < 256:
        out.append(cur)
        safety += 1
        if cur.parent_path in ("", ".", "0"):
            break
        parent_name = cur.parent_path.split("/")[-1]
        cur = nodes_by_name.get(parent_name)
    return out


def _parse_visible(node: ParsedNode) -> bool:
    v = node.raw_attrs.get("visible", "true").lower()
    return "false" not in v


def _parse_mouse_filter(node: ParsedNode) -> int:
    raw = node.raw_attrs.get("mouse_filter", "0")
    try:
        return int(raw.split("=", 1)[-1].strip())
    except ValueError:
        return 0


def summarize_control_interaction(
    nodes_by_name: dict[str, ParsedNode],
    control_name: str,
    *,
    viewport: tuple[int, int],
) -> dict:
    notes: list[str] = []
    chain = _ancestor_chain(nodes_by_name, control_name)
    ancestor_visible = all(_parse_visible(n) for n in chain[1:]) if len(chain) > 1 else True
    target = nodes_by_name.get(control_name)
    receives_mouse = True
    effectively_invisible = False
    if target:
        mf = _parse_mouse_filter(target)
        if mf == 2:
            receives_mouse = False
            notes.append("mouse_filter=IGNORE")
        mod = target.raw_attrs.get("modulate", "")
        if "Color(" in mod and ", 0)" in mod.replace(" ", ""):
            effectively_invisible = True
            notes.append("modulate alpha ~0")
    rect = control_screen_rect(nodes_by_name, control_name, viewport=viewport)
    vw, vh = viewport
    rect_in_viewport = False
    if rect:
        x, y, w, h = rect
        rect_in_viewport = w > 1 and h > 1 and x + w >= 0 and y + h >= 0 and x <= vw and y <= vh
    likelihood = "medium"
    if not ancestor_visible or not receives_mouse or effectively_invisible:
        likelihood = "none"
    elif not rect_in_viewport:
        likelihood = "low"
    return {
        "ancestor_visible": ancestor_visible,
        "receives_mouse": receives_mouse,
        "effectively_invisible": effectively_invisible,
        "rect_in_viewport": rect_in_viewport,
        "player_click_likelihood": likelihood,
        "automation_notes": notes,
    }
```

- [ ] **Step 3: 运行测试**

Run: `python -m unittest tests.test_scene_interaction_model.TestHiddenAncestor.test_button_under_invisible_ancestor_flagged -v`

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add mcp/scene_interaction_model.py tests/test_scene_interaction_model.py
git commit -m "feat(mcp): static visibility and mouse filter heuristics for controls"
```

---

### Task 4: 玩法类型与「典型操作」对照表

**Files:**
- Create: `mcp/gameplay_archetype_hints.py`
- Test: `tests/test_gameplay_archetype_hints.py`

- [ ] **Step 1: 失败测试**

```python
def test_fps_archetype_emits_move_look_shoot_when_signals_match():
    sys.path.insert(0, str(REPO / "mcp"))
    from gameplay_archetype_hints import build_gameplay_understanding

    gu = build_gameplay_understanding(
        inferred_keywords=["ui-heavy"],
        script_method_blob="shoot fire _input is_on_floor",
        scene_root_types=["Node3D", "CharacterBody3D"],
        inputmap_blob="ui_left\nui_right\n",
    )
    assert "first_person" in gu["matched_archetypes"]
    verbs = {v["verb"] for v in gu["project_verbs"]}
    assert "move" in verbs or "look" in verbs or "shoot" in verbs
```

- [ ] **Step 2: 实现 `build_gameplay_understanding`**

`mcp/gameplay_archetype_hints.py` 内建只读表（示例结构）：

```python
ARCHETYPES = [
    {
        "id": "first_person",
        "match": {"scene_types": {"CharacterBody3D", "Camera3D"}, "method_tokens": ("shoot", "fire", "weapon", "_input")},
        "typical_verbs": [
            {"verb": "move", "usual_effect": "改变角色位置"},
            {"verb": "look", "usual_effect": "改变视角朝向"},
            {"verb": "shoot", "usual_effect": "发射命中/消耗弹药等"},
        ],
    },
    {
        "id": "menu_driven",
        "match": {"keywords": {"ui-heavy"}},
        "typical_verbs": [
            {"verb": "navigate_ui", "usual_effect": "切换面板或弹窗"},
            {"verb": "confirm", "usual_effect": "提交选择或进入下一流程"},
        ],
    },
]
```

从 `project.godot` 读出 `[input]` 段原文传入 `inputmap_blob`，若存在 `ui_accept` / 自定义 `fire` 等则加入 `project_verbs`。

- [ ] **Step 3: 运行测试**

Run: `python -m unittest tests.test_gameplay_archetype_hints -v`

- [ ] **Step 4: Commit**

```bash
git add mcp/gameplay_archetype_hints.py tests/test_gameplay_archetype_hints.py
git commit -m "feat(mcp): gameplay archetype hints and verb crosswalk"
```

---

### Task 5: 并入 operational profile 文档与 index.json

**Files:**
- Modify: `mcp/operational_profile.py`
- Modify: `mcp/server.py`（若需在 `_build_context_docs` 传入 `project_godot` 路径给 bundle）
- Modify: `tests/test_operational_profile.py`

- [ ] **Step 1: 扩展 `build_operational_profile_bundle` 签名**

增加可选参数 `project_root` 已存在；在内部对 `menu_scenes` ∪ `level_scenes` 中每个 `.tscn` 调用 `parse_tscn_nodes` + 对每个 `Button` 调用 `summarize_control_interaction`，聚合为 `data["ui_interaction_model"] = {"by_scene": {...}}`。

- [ ] **Step 2: 生成 Markdown 新章节「7. UI 排布与静态可点性（启发式）」**

列出每个场景下按钮的 `player_click_likelihood` 与 `automation_notes`，并固定免责声明：不解析运行中 `visible = true` 的脚本切换。

- [ ] **Step 3: 增加章节「8. 玩法语义与同类操作对照」**

调用 `build_gameplay_understanding`，输出表格：典型操作 / 常见效果 / 本项目信号是否支持（has / weak / absent）。

- [ ] **Step 4: `index.json` 顶层增加键**

`"gameplay_understanding": {...}, "ui_interaction_model": {...}`（与 `operational_profile` 并列或嵌套在 `operational_profile` 内二选一，**全仓库统一一种**，推荐嵌套在 `operational_profile` 下避免顶层爆炸）。

- [ ] **Step 5: 测试**

Run: `python -m unittest tests.test_operational_profile -v`

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add mcp/operational_profile.py mcp/server.py tests/test_operational_profile.py
git commit -m "feat(mcp): embed interaction model and gameplay understanding in operational profile"
```

---

### Task 6: Flow 候选与「误点不到」降权

**Files:**
- Modify: `mcp/server.py`（`_derive_flow_candidates` 之后或 `design_game_basic_test_flow` 内）

- [ ] **Step 1: 在生成 `action_candidates` 时附加 `static_interaction`**

若 `index` 中已有 `ui_interaction_model.by_scene[scene].nodes[BtnName]`，合并 `player_click_likelihood` 与 `ancestor_visible`。

- [ ] **Step 2: `design_game_basic_test_flow` 排序**

在同一阶段内，优先 `likelihood in (medium, high)` 的点击候选；`none` 默认不进入 `selected_actions`（除非该阶段无其它候选且显式 `arguments.allow_low_likelihood=true`）。

- [ ] **Step 3: 测试**

扩展 `tests/test_operational_profile.py` 或新建 `tests/test_design_flow_weights.py`，构造最小 `index` 片段验证过滤顺序。

- [ ] **Step 4: Commit**

```bash
git add mcp/server.py tests/test_design_flow_weights.py
git commit -m "feat(mcp): weight basic flow actions by static click likelihood"
```

---

## Self-Review（计划自检）

1. **Spec coverage：** 场景排布、遮挡/不可点启发式、玩法类型与典型操作对照、初始化产出、MCP 理解重心从「枚举 UI」转向「玩家能做什么」——均已映射到 Task 1–6。  
2. **Placeholder scan：** 无 TBD；`summarize_control_interaction` 的「…」须在实现时用完整 Python 补全。  
3. **Type consistency：** `ParsedNode`、`build_gameplay_understanding` 返回值字段在 Task 5 写入 `index` 时需与文档模板一致，避免一处 `by_scene`、一处 `per_scene`。

---

**计划已保存至 `docs/superpowers/plans/2026-04-10-mcp-project-init-deep-understanding.md`。可选执行方式：**

**1. Subagent-Driven（推荐）** — 每个 Task 单独子代理执行，任务间人工快速核对，迭代快。  

**2. Inline Execution** — 本会话内按 Task 顺序实现，批量修改并在 Checkpoint 处停顿审查。  

**你希望采用哪一种？**
