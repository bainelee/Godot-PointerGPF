from __future__ import annotations

import json
from pathlib import Path

_CHAT_STEP_MAP_CACHE: dict[str, tuple[str, str]] | None = None
_CHAT_ACTION_MAP_CACHE: dict[str, tuple[str, str]] | None = None

_DEFAULT_CHAT_STEP_MAP: dict[str, tuple[str, str]] = {
    "prepare_new_game": ("正在开始新游戏流程", "目标：进入游戏世界并初始化本轮测试。"),
    "click_new_game": ("正在点击“新游戏”", "目标：进入存档选择并创建新流程。"),
    "click_slot0": ("正在新建并覆盖存档0", "目标：确保测试使用固定存档槽位。"),
    "wait_ingame": ("正在等待进入游戏主场景", "目标：确认已成功进入可操作状态。"),
    "set_game_speed_x6": ("正在切换为六倍速", "目标：加快流程验证时间。"),
    "start_cleanup_mode": ("正在进入清理模式", "目标：准备对目标房间发起清理。"),
    "select_cleanup_room": ("正在选择清理房间", "目标：锁定要清理的房间。"),
    "confirm_cleanup": ("正在确认清理", "目标：正式启动房间清理。"),
    "wait_clean_done": ("正在等待清理房间完成", "目标：确认房间状态变为 cleaned。"),
    "start_build_mode": ("正在进入建设模式", "目标：准备建造目标房间。"),
    "wait_research_zone_visible": ("正在等待建设分区可见", "目标：确认可选择建造分区。"),
    "select_build_zone": ("正在选择建设分区", "目标：进入指定建造类别。"),
    "select_build_room": ("正在选择建设房间", "目标：锁定要建设的房间。"),
    "wait_build_confirm_visible": ("正在等待建设确认按钮出现", "目标：确保建造可提交。"),
    "confirm_build": ("正在确认建设", "目标：正式启动建造流程。"),
    "wait_build_done": ("正在等待建设房间完成", "目标：确认房间状态变为 built。"),
    "save_game_slot0": ("正在保存游戏到存档0", "目标：写入持久化数据供继续游戏验证。"),
    "save_current_slot": ("正在保存当前存档", "目标：写入持久化数据供继续游戏验证。"),
    "click_continue": ("正在点击“继续游戏”", "目标：从已有存档恢复游戏状态。"),
    "verify_room_cleaned": ("正在验证清理结果已持久化", "目标：继续游戏后仍保持 cleaned。"),
    "verify_room_built": ("正在验证建设结果已持久化", "目标：继续游戏后仍保持 built。"),
}

_DEFAULT_CHAT_ACTION_MAP: dict[str, tuple[str, str]] = {
    "click": ("正在执行点击操作", "目标：推进到下一交互步骤。"),
    "wait": ("正在等待条件满足", "目标：确保状态达到断言前置条件。"),
    "check": ("正在执行状态校验", "目标：验证当前状态符合预期。"),
    "savegame": ("正在保存游戏", "目标：写入持久化数据供继续游戏验证。"),
    "sleep": ("正在等待短延时", "目标：给界面与状态变更留出缓冲。"),
}


def load_chat_mappings() -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    global _CHAT_STEP_MAP_CACHE, _CHAT_ACTION_MAP_CACHE
    if _CHAT_STEP_MAP_CACHE is not None and _CHAT_ACTION_MAP_CACHE is not None:
        return _CHAT_STEP_MAP_CACHE, _CHAT_ACTION_MAP_CACHE
    step_map: dict[str, tuple[str, str]] = dict(_DEFAULT_CHAT_STEP_MAP)
    action_map: dict[str, tuple[str, str]] = dict(_DEFAULT_CHAT_ACTION_MAP)
    cfg_path = Path(__file__).with_name("chat_progress_templates.json")
    if cfg_path.exists():
        try:
            payload = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            raw_steps = payload.get("step_map", {})
            raw_actions = payload.get("action_map", {})
            if isinstance(raw_steps, dict):
                for key, val in raw_steps.items():
                    if not isinstance(key, str) or not isinstance(val, dict):
                        continue
                    doing = str(val.get("doing", "")).strip()
                    goal = str(val.get("goal", "")).strip()
                    if doing and goal:
                        step_map[key.strip().lower()] = (doing, goal)
            if isinstance(raw_actions, dict):
                for key, val in raw_actions.items():
                    if not isinstance(key, str) or not isinstance(val, dict):
                        continue
                    doing = str(val.get("doing", "")).strip()
                    goal = str(val.get("goal", "")).strip()
                    if doing and goal:
                        action_map[key.strip().lower()] = (doing, goal)
    _CHAT_STEP_MAP_CACHE = step_map
    _CHAT_ACTION_MAP_CACHE = action_map
    return step_map, action_map


def human_step_and_goal(step_id: str, action: str) -> tuple[str, str]:
    sid = (step_id or "").strip().lower()
    act = (action or "").strip().lower()
    step_map, action_map = load_chat_mappings()
    if sid in step_map:
        return step_map[sid]
    if act in action_map:
        return action_map[act]
    return f"正在执行步骤 {step_id or 'unknown_step'}", "目标：持续推进流程并验证关键状态。"
