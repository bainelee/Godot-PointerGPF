"""Static operational profile for Godot projects: entry scene, scene clusters, transitions, phased UI.

Used as MCP context after init_project_context; informs basic flow design (do not mix pre/post change_scene targets).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gameplay_archetype_hints import build_gameplay_understanding_for_project
from gdscript_ready_visibility import main_scene_packed_hidden_by_scripts
from scene_interaction_model import analyze_scene_buttons, read_viewport_size_from_project

# --- project.godot ---------------------------------------------------------------------------

_MAIN_SCENE_STRING = re.compile(r"run/main_scene\s*=\s*\"(res://[^\"]+)\"")
_MAIN_SCENE_UID = re.compile(r"run/main_scene\s*=\s*\"(uid://[^\"]+)\"")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _resolve_main_scene_path(project_root: Path) -> tuple[str | None, str]:
    raw = _read_text(project_root / "project.godot")
    m_res = _MAIN_SCENE_STRING.search(raw)
    if m_res:
        rel = m_res.group(1).replace("res://", "").lstrip("/")
        return rel, "run/main_scene string path"
    m_uid = _MAIN_SCENE_UID.search(raw)
    if not m_uid:
        return None, "run/main_scene not found"
    uid = m_uid.group(1)
    for path in sorted(project_root.rglob("*.tscn")):
        try:
            head = path.read_text(encoding="utf-8")[:400]
        except OSError:
            continue
        if f'uid="{uid}"' in head:
            rel = str(path.relative_to(project_root)).replace("\\", "/")
            return rel, f"uid map ({uid})"
    return None, f"no .tscn matched uid {uid}"


# --- .tscn parsing ---------------------------------------------------------------------------

def _res_to_rel(res: str) -> str:
    return res.replace("res://", "").lstrip("/")


def _ext_id_map(tscn_text: str) -> dict[str, str]:
    """Parse ext_resource lines; Godot may place id= before or after path=."""
    out: dict[str, str] = {}
    for line in tscn_text.splitlines():
        s = line.strip()
        if not s.startswith("[ext_resource"):
            continue
        # Avoid matching the `d="` inside `uid="..."` (substring `id="`).
        id_m = re.search(r'(?<![a-zA-Z])id="([^"]+)"', s)
        path_m = re.search(r'path="(res://[^"]+)"', s)
        if id_m and path_m:
            out[id_m.group(1)] = _res_to_rel(path_m.group(1))
    return out


def _all_gd_scripts_in_tscn(project_root: Path, scene_rel: str) -> list[str]:
    text = _read_text(project_root / scene_rel)
    if not text:
        return []
    id_map = _ext_id_map(text)
    out: list[str] = []
    for m in re.finditer(r'script\s*=\s*ExtResource\("([^"]+)"\)', text):
        eid = m.group(1)
        rel = id_map.get(eid, "")
        if rel.endswith(".gd"):
            out.append(rel)
    return list(dict.fromkeys(out))


def _packed_scene_children(project_root: Path, scene_rel: str, *, max_depth: int, seen: set[str]) -> None:
    if scene_rel in seen or len(seen) > 400:
        return
    seen.add(scene_rel)
    path = project_root / scene_rel
    text = _read_text(path)
    if not text:
        return
    if max_depth <= 0:
        return
    for line in text.splitlines():
        s = line.strip()
        if 'type="PackedScene"' not in s or "path=" not in s:
            continue
        path_m = re.search(r'path="(res://[^"]+)"', s)
        if not path_m:
            continue
        child = _res_to_rel(path_m.group(1))
        if child.endswith(".tscn"):
            _packed_scene_children(project_root, child, max_depth=max_depth - 1, seen=seen)


def _scene_script_paths(project_root: Path, scene_rel: str) -> list[str]:
    return _all_gd_scripts_in_tscn(project_root, scene_rel)


# --- GDScript: scene transitions & dynamic loads -------------------------------------------

_CONST_STRING = re.compile(
    r"^\s*const\s+([A-Za-z_][A-Za-z0-9_]*)\s*:=\s*([\"'])(res://[^\"']+)\2",
    re.MULTILINE,
)
_CONST_STRING_EQ = re.compile(
    r"^\s*const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([\"'])(res://[^\"']+)\2",
    re.MULTILINE,
)


def _const_map(gd_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for rx in (_CONST_STRING, _CONST_STRING_EQ):
        for m in rx.finditer(gd_text):
            out[m.group(1)] = _res_to_rel(m.group(3))
    return out


def _change_scene_targets(gd_text: str) -> list[str]:
    cmap = _const_map(gd_text)
    prefix = r"(?:get_tree\(\)\s*\.\s*)?change_scene_to_file\s*\("
    out: list[str] = []
    for m in re.finditer(prefix + r'\s*"((?:res://)[^"]+)"\s*\)', gd_text):
        out.append(_res_to_rel(m.group(1)))
    for m in re.finditer(prefix + r"\s*'((?:res://)[^']+)'\s*\)", gd_text):
        out.append(_res_to_rel(m.group(1)))
    for m in re.finditer(prefix + r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", gd_text):
        key = m.group(1)
        if key in cmap and cmap[key].endswith(".tscn"):
            out.append(cmap[key])
    return list(dict.fromkeys(out))


def _dynamic_scene_loads(gd_text: str) -> list[str]:
    out: list[str] = []
    patterns = (
        r'preload\s*\(\s*"((?:res://)[^"]+\.tscn)"\s*\)',
        r"preload\s*\(\s*'((?:res://)[^']+\.tscn)'\s*\)",
        r'load\s*\(\s*"((?:res://)[^"]+\.tscn)"\s*\)',
        r"load\s*\(\s*'((?:res://)[^']+\.tscn)'\s*\)",
    )
    for pat in patterns:
        for m in re.finditer(pat, gd_text):
            out.append(_res_to_rel(m.group(1)))
    return list(dict.fromkeys(out))


def _scripts_referenced_by_scene_cluster(project_root: Path, scenes: set[str]) -> set[str]:
    scripts: set[str] = set()
    for sc in scenes:
        for sp in _all_gd_scripts_in_tscn(project_root, sc):
            scripts.add(sp)
    return scripts


def _merged_gd_for_scenes(project_root: Path, scenes: set[str]) -> str:
    chunks: list[str] = []
    for sc in sorted(scenes):
        for sp in _all_gd_scripts_in_tscn(project_root, sc):
            chunks.append(_read_text(project_root / sp))
    return "\n".join(chunks)


def _expand_cluster_with_dynamic_scenes(project_root: Path, scenes: set[str]) -> None:
    """Mutates scenes to include preload/load .tscn from root scripts of scenes already in cluster."""
    for sc in list(scenes):
        for sp in _scene_script_paths(project_root, sc):
            text = _read_text(project_root / sp)
            for rel in _dynamic_scene_loads(text):
                if (project_root / rel).exists():
                    scenes.add(rel)
                    _packed_scene_children(project_root, rel, max_depth=14, seen=scenes)


def _build_menu_cluster(project_root: Path, main_rel: str | None) -> set[str]:
    scenes: set[str] = set()
    if main_rel and (project_root / main_rel).exists():
        _packed_scene_children(project_root, main_rel, max_depth=16, seen=scenes)
        scenes.add(main_rel)
    return scenes


def _build_level_cluster(project_root: Path, menu_scenes: set[str]) -> tuple[set[str], list[dict[str, Any]]]:
    menu_scripts = _scripts_referenced_by_scene_cluster(project_root, menu_scenes)
    transitions: list[dict[str, Any]] = []
    level_roots: set[str] = set()
    for srel in sorted(menu_scripts):
        text = _read_text(project_root / srel)
        for tgt in _change_scene_targets(text):
            if tgt.endswith(".tscn") and (project_root / tgt).exists():
                transitions.append({"script": srel, "target_scene": tgt, "mechanism": "change_scene_to_file"})
                level_roots.add(tgt)
    level_scenes: set[str] = set()
    for root in level_roots:
        _packed_scene_children(project_root, root, max_depth=16, seen=level_scenes)
        level_scenes.add(root)
    _expand_cluster_with_dynamic_scenes(project_root, level_scenes)
    return level_scenes, transitions


def _infer_game_summary(keywords: list[str], level_scenes: set[str], script_method_blob: str) -> str:
    parts: list[str] = []
    corpus = " ".join(keywords).lower() + " " + script_method_blob.lower()
    if "ui-heavy" in keywords or "/ui/" in corpus:
        parts.append("含较多 UI / 菜单或面板交互")
    if level_scenes:
        parts.append("含独立关卡场景树（可与主菜单通过 change_scene 切换）")
    if "fps" in corpus or "characterbody" in corpus or "bullet" in corpus:
        parts.append("含第一人称或 3D 角色/射击相关脚本特征（静态）")
    if not parts:
        parts.append("Godot 项目（由目录与场景静态推断）")
    return "；".join(parts) if parts else "Godot 项目"


def _button_nodes_for_scenes(
    project_root: Path,
    scene_signals: dict[str, Any],
    scene_filter: set[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for btn in scene_signals.get("button_nodes", []):
        if not isinstance(btn, dict):
            continue
        sc = str(btn.get("scene", "")).replace("\\", "/")
        if sc in scene_filter:
            out.append(btn)
    return out


def _guess_button_effect(cluster_gd_blob: str, btn: dict[str, Any]) -> str:
    """Heuristic using merged GDScript from all scenes in the same runtime phase cluster."""
    name = str(btn.get("name", ""))
    gd = cluster_gd_blob
    if not gd.strip():
        return "（未绑定到已解析脚本，或需人工确认）"
    low = gd.lower()
    token = name.replace("Button", "").lower()
    if "start" in name.lower() or "开始" in gd:
        if "change_scene" in low:
            return "触发场景切换（进入下一运行阶段）"
        return "可能开始游戏或关闭开始界面"
    if "openui2" in name.lower():
        return "打开/显示关联的弹层或子 UI（同场景树内）"
    if "close" in name.lower():
        return "关闭或隐藏当前 UI 区域"
    if "mode" in name.lower():
        return "切换模式或调用玩家/指针相关逻辑（常见于 HUD）"
    return "触发脚本中 `pressed` 所连接的逻辑（需对照对应 .gd）"


def _collect_design_docs(project_root: Path, limit: int = 24) -> list[dict[str, str]]:
    docs_dir = project_root / "docs"
    if not docs_dir.is_dir():
        return []
    out: list[dict[str, str]] = []
    for path in sorted(docs_dir.rglob("*.md")):
        rel = str(path.relative_to(project_root)).replace("\\", "/")
        text = _read_text(path)
        title = ""
        for line in text.splitlines()[:12]:
            if line.startswith("# "):
                title = line[2:].strip()
                break
        excerpt = "\n".join(text.splitlines()[:18]).strip()
        if len(excerpt) > 1200:
            excerpt = excerpt[:1200] + "\n…"
        out.append({"path": rel, "title": title or rel, "excerpt": excerpt})
        if len(out) >= limit:
            break
    return out


@dataclass
class OperationalProfileResult:
    data: dict[str, Any]
    markdown: str


def build_operational_profile_bundle(
    project_root: Path,
    *,
    script_signals: dict[str, Any],
    scene_signals: dict[str, Any],
    inferred_keywords: list[str],
) -> OperationalProfileResult:
    main_rel, main_resolved_how = _resolve_main_scene_path(project_root)
    menu_scenes = _build_menu_cluster(project_root, main_rel)
    level_scenes, transitions = _build_level_cluster(project_root, menu_scenes)

    menu_gd_blob = _merged_gd_for_scenes(project_root, menu_scenes)
    level_gd_blob = _merged_gd_for_scenes(project_root, level_scenes)

    menu_buttons = _button_nodes_for_scenes(project_root, scene_signals, menu_scenes)
    level_buttons = _button_nodes_for_scenes(project_root, scene_signals, level_scenes)

    cross_warnings: list[str] = []
    if transitions:
        cross_warnings.append(
            "检测到 `change_scene_to_file`（或等价常量）：主场景树在切换后会被替换，"
            "仅属于菜单阶段的按钮不会与新场景共存，不可与关卡内 HUD 混在同一步序中。"
        )
    menu_btn_scenes = {str(b.get("scene", "")) for b in menu_buttons}
    level_btn_scenes = {str(b.get("scene", "")) for b in level_buttons}
    overlap = menu_btn_scenes & level_btn_scenes
    if overlap:
        cross_warnings.append(f"下列场景的按钮同时被划入多阶段（需复查）: {sorted(overlap)[:8]}")

    method_blob = " ".join(str(x) for x in script_signals.get("method_samples", []) if isinstance(x, str))
    game_summary = _infer_game_summary(inferred_keywords, level_scenes, method_blob)
    design_docs = _collect_design_docs(project_root)

    phases: list[dict[str, Any]] = [
        {
            "id": "entry_menu",
            "label": "启动后首屏（主场景及其 PackedScene 子树）",
            "scene_files": sorted(menu_scenes),
            "buttons": [
                {
                    "scene": b.get("scene"),
                    "node": b.get("name"),
                    "type": b.get("type"),
                    "inferred_effect": _guess_button_effect(menu_gd_blob, b),
                }
                for b in menu_buttons[:80]
            ],
        },
        {
            "id": "post_scene_change",
            "label": "场景切换后的运行阶段（由脚本中的 change_scene 目标及其子树、代码实例化场景组成）",
            "scene_files": sorted(level_scenes),
            "scene_transitions": transitions,
            "buttons": [
                {
                    "scene": b.get("scene"),
                    "node": b.get("name"),
                    "type": b.get("type"),
                    "inferred_effect": _guess_button_effect(level_gd_blob, b),
                }
                for b in level_buttons[:80]
            ],
        },
    ]

    vw_vh = read_viewport_size_from_project(project_root / "project.godot")
    hidden_packed: dict[str, bool] = {}
    if main_rel:
        hidden_packed = main_scene_packed_hidden_by_scripts(project_root, main_rel)
    ui_by_scene: dict[str, Any] = {}
    for sc in sorted(menu_scenes | level_scenes):
        rel = str(sc).replace("\\", "/")
        if rel.endswith(".tscn"):
            ui_by_scene[rel] = analyze_scene_buttons(
                project_root,
                rel,
                vw_vh,
                external_instance_root_hidden=bool(hidden_packed.get(rel)),
            )

    root_types = sorted(
        {
            str(x.get("root_type", ""))
            for x in scene_signals.get("root_nodes", [])
            if isinstance(x, dict) and str(x.get("root_type", "")).strip()
        }
    )
    gameplay_understanding = build_gameplay_understanding_for_project(
        project_root,
        inferred_keywords=inferred_keywords,
        script_method_blob=method_blob,
        scene_root_types=root_types,
    )

    data: dict[str, Any] = {
        "analysis_method": "static_tscn_gdscript",
        "disclaimer": (
            "本分析基于 project.godot、.tscn 与 .gd 的静态解析，不替代真实运行；"
            "动态生成节点、资源包内场景或编辑器插件写入的行为可能未体现。"
        ),
        "main_scene": {"path": main_rel, "resolved_via": main_resolved_how},
        "game_identity": {
            "summary": game_summary,
            "inferred_keywords": list(inferred_keywords),
        },
        "runtime_phases": phases,
        "cross_phase_warnings": cross_warnings,
        "design_documents": design_docs,
        "mcp_usage": {
            "primary_context_file": "pointer_gpf/project_context/06-operational-profile.md",
            "basic_flow_game_type_reference": "docs/mcp-basic-test-flow-game-type-expectations.md",
            "basic_flow_usage_and_nl_reference": "docs/mcp-basic-test-flow-reference-usage.md",
            "rules": [
                "基础测试流程应显式区分「菜单阶段」与「切换后阶段」，中间步骤应对齐真实 `change_scene` 触发控件（例如开始游戏）。",
                "仅出现在菜单子树中的 UI 步骤，必须在切换场景之前执行；关卡 HUD 步骤仅能在切换之后执行。",
                "若与设计文档冲突，以设计文档为准并应刷新本分析（refresh_project_context）。",
                "生成或扩写基础测试流程时，应对照 PointerGPF 仓库 `docs/mcp-basic-test-flow-game-type-expectations.md` 与本工程 `04-flow-authoring-guide.md` 中的「按游戏类型」小节；在 `flow_candidates` 与静态可点性证据允许时，优先用较少步骤覆盖「进入可玩态 → 一条核心交互 → 可观察结果」，未完成的功能不要写进步骤。",
            ],
        },
        "ui_interaction_model": {
            "viewport": {"w": vw_vh[0], "h": vw_vh[1]},
            "by_scene": ui_by_scene,
            "packed_scenes_hidden_by_main_ready": hidden_packed,
        },
        "gameplay_understanding": gameplay_understanding,
    }

    md_lines: list[str] = [
        "# 运行与操作依据（Operational Profile）",
        "",
        f"- 生成方式: `{data['analysis_method']}`",
        f"- 主场景: `{main_rel or '(unknown)'}`（解析: {main_resolved_how}）",
        "",
        "## 1. 项目是什么（静态推断）",
        "",
        f"- 概要: {game_summary}",
        f"- 关键词: {', '.join(f'`{k}`' for k in inferred_keywords) or '`(none)`'}",
        "",
        "## 2. 运行入口与阶段划分",
        "",
        "### 阶段 A — 启动后首屏（菜单 / 主界面）",
        "",
        f"- 包含场景文件数: {len(menu_scenes)}",
        "- 主要场景:",
        *(f"  - `{s}`" for s in sorted(menu_scenes)[:40]),
        *(["  - …"] if len(menu_scenes) > 40 else []),
        "",
        "**可点击控件（节选）**",
        "",
    ]
    if menu_buttons:
        for b in menu_buttons[:35]:
            eff = _guess_button_effect(menu_gd_blob, b)
            md_lines.append(f"- `{b.get('scene')}` / `{b.get('name')}` ({b.get('type')}): {eff}")
    else:
        md_lines.append("- （未在扫描结果中列出按钮；可能无 UI 或场景未纳入扫描根）")
    md_lines.extend(["", "### 场景切换（脚本证据）", ""])
    if transitions:
        for t in transitions:
            md_lines.append(f"- `{t['script']}` → `{t['target_scene']}`（{t['mechanism']}）")
    else:
        md_lines.append("- （未从挂载于首屏簇的脚本中解析到 `change_scene_to_file`）")
    md_lines.extend(
        [
            "",
            "### 阶段 B — 切换后的关卡 / 运行场景",
            "",
            f"- 包含场景文件数: {len(level_scenes)}",
            "- 主要场景:",
            *(f"  - `{s}`" for s in sorted(level_scenes)[:40]),
            *(["  - …"] if len(level_scenes) > 40 else []),
            "",
            "**可点击控件（节选）**",
            "",
        ]
    )
    if level_buttons:
        for b in level_buttons[:35]:
            eff = _guess_button_effect(level_gd_blob, b)
            md_lines.append(f"- `{b.get('scene')}` / `{b.get('name')}` ({b.get('type')}): {eff}")
    else:
        md_lines.append("- （未列出；可能关卡 UI 由代码 `preload`/`load` 挂载，见上表阶段 B 场景列表）")
    md_lines.extend(["", "## 3. 跨阶段约束（MCP 操作必须遵守）", ""])
    for w in cross_warnings:
        md_lines.append(f"- {w}")
    if not cross_warnings:
        md_lines.append("- 未检测到跨场景切换信号；仍建议以场景树为单位规划步骤。")
    md_lines.extend(["", "## 4. 项目内设计文档（若存在）", ""])
    if design_docs:
        for d in design_docs:
            md_lines.append(f"- `{d['path']}` — {d['title']}")
            md_lines.append("")
            md_lines.append("```")
            md_lines.append(d["excerpt"])
            md_lines.append("```")
            md_lines.append("")
    else:
        md_lines.append("- 未发现 `docs/**/*.md`（可在项目中添加设计说明以供后续初始化引用）")

    md_lines.extend(
        [
            "",
            "## 7. UI 排布与静态可点性（启发式）",
            "",
            f"- 假定视口: `{vw_vh[0]}×{vw_vh[1]}`（来自 `project.godot`，缺省为 1920×1080）",
            "- **已纳入（静态）**：",
            "  - 当前 `.tscn` 挂载的 `.gd` 中 `func _ready` 里对 `某节点.visible =` 的赋值（含 `@onready var x = $Child` 映射）。",
            "  - 主场景中脚本对 **PackedScene 实例节点**（如 `UI1`）在 `_ready` 里设为 `visible=false` 时，会标记对应子 `.tscn` 整段在启动时不可点。",
            "  - 同父节点下 **文件中靠后的兄弟控件** 若与按钮矩形相交，会提示可能被遮挡（**未**解析 `z_index` / 主题最小尺寸 / 容器布局）。",
            "- **仍未纳入**：运行中后续帧、信号回调、动画、状态机、`call_deferred`、跨场景动态 `instance()` 等对 `visible`/`mouse_filter` 的修改；像素级绘制顺序。",
            "",
        ]
    )
    if ui_by_scene:
        shown = 0
        for sc in sorted(ui_by_scene.keys()):
            payload = ui_by_scene[sc]
            btns = payload.get("buttons") or {}
            if not btns:
                continue
            md_lines.append(f"### `{sc}`")
            for btn, sm in sorted(btns.items()):
                lk = sm.get("player_click_likelihood", "")
                notes = sm.get("automation_notes") or []
                note_s = ("；" + "；".join(str(x) for x in notes)) if notes else ""
                md_lines.append(f"- `{btn}` → 静态可点性: `{lk}`{note_s}")
            md_lines.append("")
            shown += 1
            if shown >= 28:
                md_lines.append("- …（更多场景已写入 `index.json` → `operational_profile.ui_interaction_model`）")
                break
    else:
        md_lines.append("- （无 `.tscn` 场景可分析）")

    md_lines.extend(["", "## 8. 玩法语义与同类操作对照", ""])
    matched = gameplay_understanding.get("matched_archetypes") or []
    md_lines.append(f"- 匹配到的静态原型: {', '.join(f'`{m}`' for m in matched) or '`(none)`'}")
    md_lines.append("")
    md_lines.append("| 操作动词 | 常见效果 | 静态支持 |")
    md_lines.append("|----------|----------|----------|")
    for v in gameplay_understanding.get("project_verbs", []):
        md_lines.append(
            f"| `{v.get('verb', '')}` | {v.get('usual_effect', '')} | `{v.get('support', '')}` |"
        )
    md_lines.append("")
    md_lines.append(f"- {gameplay_understanding.get('disclaimer', '')}")

    md_lines.extend(
        [
            "",
            "## 5. 能力边界说明",
            "",
            f"- {data['disclaimer']}",
            "",
            "## 6. 与基础测试流程生成的关系",
            "",
            "- `design_game_basic_test_flow` 应优先使用本文件中的阶段划分：",
            "  - 「进入游戏」类步骤必须对应阶段 A 中能触发 `change_scene` 的控件（若存在）。",
            "  - 阶段 B 的 HUD 仅能在上述切换之后编排。",
            "- 按游戏类型的**流程预期（思考参照）**：PointerGPF 仓库 `docs/mcp-basic-test-flow-game-type-expectations.md`；目标工程内每次初始化后的 `04-flow-authoring-guide.md` 含精简速查。",
            "  - 与 §8「玩法语义」对照，可判断更接近哪类游戏，从而在步数预算内优先选「核心玩法」相关候选。",
            "- **使用方式与自然语言触发**：`docs/mcp-basic-test-flow-reference-usage.md`；MCP 工具 `get_basic_test_flow_reference_guide` 可返回该说明全文，`route_nl_intent` 可解析「基础测试流程怎么用」等说法。",
            "",
        ]
    )

    return OperationalProfileResult(data=data, markdown="\n".join(md_lines) + "\n")


def split_flow_candidates_by_phase(
    flow_candidates: dict[str, Any],
    op_data: dict[str, Any],
) -> dict[str, Any]:
    """Split action/assertion candidates into menu / level / unknown using operational_profile.runtime_phases."""
    phases = op_data.get("runtime_phases") if isinstance(op_data, dict) else None
    if not isinstance(phases, list) or len(phases) < 2:
        return {"enabled": False, "menu_actions": [], "level_actions": [], "menu_assertions": [], "level_assertions": []}

    menu_scenes = set(str(x) for x in (phases[0].get("scene_files") or []) if x)
    level_scenes = set(str(x) for x in (phases[1].get("scene_files") or []) if x)

    def scene_from_evidence(ev: str) -> str | None:
        if ev.startswith("scene_button:"):
            rest = ev[len("scene_button:") :]
            idx = rest.rfind(":")
            if idx <= 0:
                return None
            return rest[:idx].replace("\\", "/")
        if ev.startswith("scene_control:"):
            rest = ev[len("scene_control:") :]
            idx = rest.rfind(":")
            if idx <= 0:
                return None
            return rest[:idx].replace("\\", "/")
        return None

    def classify_candidate(item: dict[str, Any]) -> str:
        evs = item.get("evidence") or []
        if not isinstance(evs, list):
            return "unknown"
        scenes_found: set[str] = set()
        for ev in evs:
            if not isinstance(ev, str):
                continue
            sc = scene_from_evidence(ev)
            if sc:
                scenes_found.add(sc)
        if not scenes_found:
            return "unknown"
        in_menu = bool(scenes_found & menu_scenes)
        in_level = bool(scenes_found & level_scenes)
        if in_menu and not in_level:
            return "menu"
        if in_level and not in_menu:
            return "level"
        if in_menu and in_level:
            return "unknown"
        return "unknown"

    actions = [x for x in flow_candidates.get("action_candidates", []) if isinstance(x, dict)]
    assertions = [x for x in flow_candidates.get("assertion_candidates", []) if isinstance(x, dict)]

    menu_actions = [a for a in actions if classify_candidate(a) == "menu"]
    level_actions = [a for a in actions if classify_candidate(a) == "level"]
    menu_assertions = [a for a in assertions if classify_candidate(a) == "menu"]
    level_assertions = [a for a in assertions if classify_candidate(a) == "level"]

    return {
        "enabled": True,
        "menu_scenes": sorted(menu_scenes),
        "level_scenes": sorted(level_scenes),
        "menu_actions": menu_actions,
        "level_actions": level_actions,
        "menu_assertions": menu_assertions,
        "level_assertions": level_assertions,
    }


def pick_enter_game_candidate(menu_actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer Start / Play / 开始 game entry."""
    if not menu_actions:
        return None
    non_none = [
        a
        for a in menu_actions
        if str((a.get("static_interaction") or {}).get("player_click_likelihood", "medium")) != "none"
    ]
    pool = non_none if non_none else menu_actions
    scored: list[tuple[int, dict[str, Any]]] = []
    for a in pool:
        hid = str(a.get("id", "")).lower()
        hint = str(a.get("hint", "")).lower()
        th = str(a.get("target_hint", "")).lower()
        blob = f"{hid} {hint} {th}"
        score = 0
        if "start" in blob:
            score += 5
        if "play" in blob:
            score += 4
        if "begin" in blob:
            score += 3
        if "开始" in blob or "startbutton" in blob.replace("`", ""):
            score += 6
        scored.append((score, a))
    scored.sort(key=lambda x: -x[0])
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return pool[0]
