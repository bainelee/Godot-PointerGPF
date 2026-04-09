"""Minimal bug-fix strategy registry (diagnosis + optional patch hooks)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

_GD_PASS_ONLY_PRESSED_HANDLER = re.compile(
    r"(^[ \t]*func[ \t]+(_on_\w*pressed)[ \t]*\([^)]*\)[ \t]*(?:->[ \t]*[\w.]+[ \t]*)?:[ \t]*\r?\n)"
    r"([ \t]*)pass[ \t]*(?:#.*)?(\r?\n|\Z)",
    re.MULTILINE,
)


class BugFixStrategy(Protocol):
    strategy_id: str

    def matches(self, issue: str) -> bool: ...

    def diagnose(self, issue: str, verification: dict[str, Any]) -> dict[str, Any]: ...

    def apply_patch(self, project_root: Path, diagnosis: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class ButtonNotClickableStrategy:
    strategy_id: str = "button_not_clickable"

    def matches(self, issue: str) -> bool:
        text = str(issue or "").strip().lower()
        if not text:
            return False
        cn_button = "按钮" in text
        cn_blocked = any(k in text for k in ("不可点击", "无法点击", "点不了", "按不了", "没反应"))
        en = "button" in text and any(
            k in text for k in ("not clickable", "cannot click", "does not respond", "unresponsive", "disabled")
        )
        return (cn_button and cn_blocked) or en

    def diagnose(self, issue: str, verification: dict[str, Any]) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "summary": "疑似按钮不可点击：优先检查遮挡、disabled/mouse_filter、焦点与上层 Control。",
            "checks": [
                "确认 TextureButton/Button.disabled 是否为 true",
                "确认 Control.mouse_filter 是否阻断点击（MOUSE_FILTER_STOP/IGNORE 误用）",
                "确认是否有全屏 ColorRect/Panel 盖在按钮上",
                "确认是否在暂停树 process_mode 下未处理输入",
            ],
            "issue_excerpt": str(issue or "").strip()[:500],
            "verification_hint": (verification.get("app_error") or {}).get("message")
            or verification.get("status")
            or "",
        }

    def apply_patch(self, project_root: Path, diagnosis: dict[str, Any]) -> dict[str, Any]:
        _ = diagnosis
        root = project_root.resolve()
        if not root.is_dir():
            return {
                "applied": False,
                "reason": "project_root 不是有效目录。",
                "changed_files": [],
            }

        for gd_path in sorted(root.rglob("*.gd")):
            if ".godot" in gd_path.parts:
                continue
            try:
                text = gd_path.read_text(encoding="utf-8")
            except OSError:
                continue
            m = _GD_PASS_ONLY_PRESSED_HANDLER.search(text)
            if not m:
                continue

            def _repl(match: re.Match) -> str:
                head, fname, ind, tail = match.group(1), match.group(2), match.group(3), match.group(4)
                stmt = f'{ind}print("[gpf-auto-fix] {fname} invoked")\n'
                return f"{head}{stmt}{tail}"

            new_text, n = _GD_PASS_ONLY_PRESSED_HANDLER.subn(_repl, text, count=1)
            if n != 1 or new_text == text:
                return {
                    "applied": False,
                    "reason": "匹配到疑似桩函数但替换未生效，已中止以免写入不一致。",
                    "changed_files": [],
                }
            try:
                gd_path.write_text(new_text, encoding="utf-8")
            except OSError as exc:
                return {
                    "applied": False,
                    "reason": f"写入失败: {gd_path}: {exc}",
                    "changed_files": [],
                }
            return {
                "applied": True,
                "changed_files": [str(gd_path.resolve())],
                "notes": f"已将空按钮处理器 {m.group(2)} 中的 pass 替换为 print，便于确认输入链路。",
            }

        return {
            "applied": False,
            "reason": (
                "未在项目 .gd 脚本中找到「函数名为 _on_*pressed 且函数体仅含 pass」的处理器；"
                "请手动接线信号或调整函数名/缩进后重试。"
            ),
            "changed_files": [],
        }


DEFAULT_STRATEGIES: tuple[BugFixStrategy, ...] = (ButtonNotClickableStrategy(),)


def select_strategy(issue: str, strategies: tuple[BugFixStrategy, ...] | None = None) -> BugFixStrategy | None:
    pool = strategies if strategies is not None else DEFAULT_STRATEGIES
    for s in pool:
        if s.matches(issue):
            return s
    return None


def default_diagnosis(issue: str, verification: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_id": "generic",
        "summary": "未匹配到专用策略；保留验证失败信息供人工处理。",
        "issue_excerpt": str(issue or "").strip()[:500],
        "verification_status": verification.get("status"),
        "app_error": verification.get("app_error"),
    }


def run_diagnosis(issue: str, verification: dict[str, Any]) -> dict[str, Any]:
    picked = select_strategy(issue)
    if picked is None:
        return default_diagnosis(issue, verification)
    return picked.diagnose(issue, verification)


def run_apply_patch(
    project_root: Path,
    issue: str,
    diagnosis: dict[str, Any],
    strategies: tuple[BugFixStrategy, ...] | None = None,
) -> dict[str, Any]:
    sid = str(diagnosis.get("strategy_id", "")).strip()
    pool = strategies if strategies is not None else DEFAULT_STRATEGIES
    for s in pool:
        if s.strategy_id == sid:
            return s.apply_patch(project_root, diagnosis)
    picked = select_strategy(issue, pool)
    if picked is None:
        return {
            "applied": False,
            "notes": "无可用策略执行补丁。",
        }
    return picked.apply_patch(project_root, diagnosis)
