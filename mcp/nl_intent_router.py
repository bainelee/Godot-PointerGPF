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
    if "基础测试流程" in norm and any(k in norm for k in ("跑", "执行", "运行")):
        return IntentRoute("run_game_basic_test_flow_by_current_state", "basic_flow_run_fuzzy")
    if "基础测试流程" in norm and any(k in norm for k in ("设计", "生成", "创建")):
        return IntentRoute("design_game_basic_test_flow", "basic_flow_design_fuzzy")
    return IntentRoute("unknown", "no_match")
