"""Natural language intent routing for MCP tool aliases."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentRoute:
    target_tool: str
    reason: str


_ALIASES: dict[str, IntentRoute] = {
    "设计一个基础测试流程": IntentRoute("design_game_basic_test_flow", "basic_flow_design"),
    "生成基础测试流程": IntentRoute("design_game_basic_test_flow", "basic_flow_design"),
    "跑一遍基础测试流程": IntentRoute("run_game_basic_test_flow_by_current_state", "basic_flow_run"),
    "要求跑基础测试流程": IntentRoute("run_game_basic_test_flow_by_current_state", "basic_flow_run"),
}


def route_nl_intent(text: str) -> IntentRoute:
    norm = str(text or "").strip()
    if norm in _ALIASES:
        return _ALIASES[norm]

    def ha(*keys: str) -> bool:
        return any(k in norm for k in keys)

    # --- Run / verify (broader phrasing than fixed aliases) ---
    run_verbs = ("跑", "执行", "运行", "验证", "检查", "走一遍", "测一下", "试一下")
    run_context = (
        "基础测试流程",
        "基础流程",
        "开局",
        "版本",
        "这版",
        "游戏",
        "冒烟",
        "smoke",
        "流程",
        "主菜单",
        "开始游戏",
    )
    if ha(*run_verbs) and ha(*run_context):
        return IntentRoute("run_game_basic_test_flow_by_current_state", "run_play_check_fuzzy")

    if ha("还能", "正常玩", "能不能玩", "是否正常") and ha("版本", "游戏", "这版", "当前", "大改", "正常玩"):
        return IntentRoute("run_game_basic_test_flow_by_current_state", "play_sanity_fuzzy")

    if ha("开局", "开始游戏", "主菜单", "进入游戏") and ha("流程", "测试", "检查", "走一遍"):
        return IntentRoute("run_game_basic_test_flow_by_current_state", "opening_fuzzy")

    # --- Design ---
    if "基础测试流程" in norm and ha("设计", "生成", "创建"):
        return IntentRoute("design_game_basic_test_flow", "basic_flow_design_fuzzy")
    if ha("设计", "生成", "创建", "做一个") and ("基础流程" in norm) and not ha("跑", "执行", "运行", "验证", "检查", "走一遍"):
        return IntentRoute("design_game_basic_test_flow", "basic_flow_alt_design_fuzzy")

    # --- Basic flow reference: usage + game-type doc pointers (before auto_fix / figma) ---
    if ha("流程预期", "游戏类型流程预期", "类型参照", "类型测试参照") and ha(
        "说明", "文档", "查看", "告诉", "哪里", "在哪", "参照", "怎么"
    ):
        return IntentRoute("get_basic_test_flow_reference_guide", "basic_flow_ref_doc_fuzzy")
    if ("基础测试流程" in norm or "基础流程" in norm) and ha(
        "怎么用",
        "如何使用",
        "使用说明",
        "说明文档",
        "文档在哪",
        "在哪看",
        "查看说明",
        "参照说明",
        "说明",
    ) and not ha("设计", "生成", "创建", "跑", "执行", "运行", "验证", "检查", "走一遍", "测一下", "试一下"):
        return IntentRoute("get_basic_test_flow_reference_guide", "basic_flow_ref_usage_fuzzy")

    # --- Auto fix (avoid matching unrelated "debug" via bare "bug") ---
    if ha("自动修复", "自动修", "帮我修", "修一下") and ha("点不了", "无法点击", "没反应", "按不了", "不可点击"):
        return IntentRoute("auto_fix_game_bug", "auto_fix_fuzzy")
    if ha("按钮", "button") and ha("点不了", "无法点击", "没反应", "按不了") and ha("自动", "修复", "修"):
        return IntentRoute("auto_fix_game_bug", "auto_fix_button_fuzzy")

    # --- Figma / UI compare ---
    if ha("figma", "设计稿", "界面", "UI", "ui", "画面") and ha("对比", "比较", "对照", "核查"):
        return IntentRoute("compare_figma_game_ui", "figma_compare_fuzzy")

    # --- Legacy fuzzy (keep after broader rules) ---
    if "基础测试流程" in norm and ha("跑", "执行", "运行"):
        return IntentRoute("run_game_basic_test_flow_by_current_state", "basic_flow_run_fuzzy")

    return IntentRoute("unknown", "no_match")
