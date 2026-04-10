"""Minimal bug-fix strategy registry (diagnosis + optional patch hooks)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

_GD_PASS_ONLY_PRESSED_HANDLER = re.compile(
    r"(^[ \t]*func[ \t]+(_on_\w*pressed)[ \t]*\([^)]*\)[ \t]*(?:->[ \t]*[\w.]+[ \t]*)?:[ \t]*\r?\n)"
    r"([ \t]*)pass[ \t]*(?:#.*)?(\r?\n|\Z)",
    re.MULTILINE,
)

_TSCN_DISABLED_TRUE = re.compile(r"(^[ \t]*)disabled[ \t]*=[ \t]*true[ \t]*$", re.MULTILINE)
_TSCN_MOUSE_FILTER_ZERO = re.compile(r"(^[ \t]*)mouse_filter[ \t]*=[ \t]*0[ \t]*$", re.MULTILINE)

_DEFAULT_PLUGIN_ID = "pointer_gpf"
_BRIDGE_AUTOLOAD_NAME = "PointerGPFRuntimeBridge"
_BRIDGE_AUTOLOAD_PATH = f"*res://addons/{_DEFAULT_PLUGIN_ID}/runtime_bridge.gd"


def _verification_augmented_issue(issue: str, verification: dict[str, Any] | None) -> str:
    parts = [str(issue or "").strip()]
    if verification:
        ae = verification.get("app_error")
        if isinstance(ae, dict):
            parts.append(str(ae.get("message", "")))
            parts.append(str(ae.get("code", "")))
        parts.append(str(verification.get("status", "")))
    return " ".join(p for p in parts if p)


def _ensure_pointer_gpf_runtime_autoload(project_root: Path) -> dict[str, Any]:
    project_cfg = project_root / "project.godot"
    if not project_cfg.exists():
        return {"ok": False, "reason": "missing project.godot", "changed_files": []}
    text = project_cfg.read_text(encoding="utf-8")
    if "[autoload]" not in text:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n[autoload]\n"
        text += f'{_BRIDGE_AUTOLOAD_NAME}="{_BRIDGE_AUTOLOAD_PATH}"\n'
        project_cfg.write_text(text, encoding="utf-8")
        return {"ok": True, "mode": "section_created", "changed_files": [str(project_cfg.resolve())]}
    lines = text.splitlines()
    section_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == "[autoload]":
            section_idx = i
            break
    if section_idx < 0:
        return {"ok": False, "reason": "no autoload section", "changed_files": []}
    key_idx = -1
    for i in range(section_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            break
        if stripped.startswith(f"{_BRIDGE_AUTOLOAD_NAME}="):
            key_idx = i
            break
    desired = f'{_BRIDGE_AUTOLOAD_NAME}="{_BRIDGE_AUTOLOAD_PATH}"'
    if key_idx < 0:
        lines.insert(section_idx + 1, desired)
        project_cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"ok": True, "mode": "key_created", "changed_files": [str(project_cfg.resolve())]}
    if lines[key_idx].strip() == desired:
        return {"ok": True, "mode": "already_enabled", "changed_files": []}
    lines[key_idx] = desired
    project_cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "mode": "key_updated", "changed_files": [str(project_cfg.resolve())]}


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


@dataclass
class SignalDisconnectedHintStrategy:
    strategy_id: str = "signal_disconnected_hint"

    def matches(self, issue: str) -> bool:
        raw = str(issue or "").strip()
        if not raw:
            return False
        low = raw.lower()
        sig = "信号" in raw or "signal" in low
        disc = any(
            k in raw for k in ("未连接", "没连线", "没接上", "断开")
        ) or "not connected" in low or "disconnect" in low
        return sig and disc

    def diagnose(self, issue: str, verification: dict[str, Any]) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "summary": "疑似 UI 信号未连接到脚本：请在检查器中确认 pressed/pressed 等信号是否已绑定。",
            "checks": [
                "在场景树选中按钮，检查「节点」面板信号页是否为空连接",
                "确认目标脚本路径与函数名是否存在拼写错误",
            ],
            "issue_excerpt": str(issue or "").strip()[:500],
            "verification_hint": (verification.get("app_error") or {}).get("message")
            or verification.get("status")
            or "",
        }

    def apply_patch(self, project_root: Path, diagnosis: dict[str, Any]) -> dict[str, Any]:
        _ = diagnosis
        root = project_root.resolve()
        reports = root / "pointer_gpf" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        out = reports / "gpf_signal_hint.json"
        payload = {
            "strategy_id": self.strategy_id,
            "hint": "请手动在 Godot 检查器中为按钮连接 pressed 等信号到目标函数。",
        }
        try:
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            return {"applied": False, "reason": f"写入失败: {out}: {exc}", "changed_files": []}
        return {
            "applied": True,
            "changed_files": [str(out.resolve())],
            "notes": "已写入信号排查提示文件（未自动改场景，以免误连）。",
        }


@dataclass
class SceneButtonDisabledFalseStrategy:
    strategy_id: str = "scene_button_disabled_false"

    def matches(self, issue: str) -> bool:
        raw = str(issue or "").strip()
        if not raw:
            return False
        low = raw.lower()
        disabled_kw = any(k in raw for k in ("禁用", "灰掉", "灰色", "不可点")) or "disabled" in low
        button_kw = "按钮" in raw or "button" in low
        return disabled_kw and button_kw

    def diagnose(self, issue: str, verification: dict[str, Any]) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "summary": "疑似场景里 Button/TextureButton 的 disabled 为 true。",
            "checks": ["在 .tscn 或检查器中确认 disabled 属性"],
            "issue_excerpt": str(issue or "").strip()[:500],
            "verification_hint": (verification.get("app_error") or {}).get("message")
            or verification.get("status")
            or "",
        }

    def apply_patch(self, project_root: Path, diagnosis: dict[str, Any]) -> dict[str, Any]:
        _ = diagnosis
        root = project_root.resolve()
        for tscn in sorted(root.rglob("*.tscn")):
            if ".godot" in tscn.parts:
                continue
            try:
                text = tscn.read_text(encoding="utf-8")
            except OSError:
                continue
            if "disabled = true" not in text:
                continue
            new_text, n = _TSCN_DISABLED_TRUE.subn(r"\1disabled = false", text, count=1)
            if n != 1:
                continue
            try:
                tscn.write_text(new_text, encoding="utf-8")
            except OSError as exc:
                return {"applied": False, "reason": f"写入失败: {tscn}: {exc}", "changed_files": []}
            return {
                "applied": True,
                "changed_files": [str(tscn.resolve())],
                "notes": "已将首个 disabled = true 改为 false（请确认目标节点正确）。",
            }
        return {"applied": False, "reason": "未找到含 disabled = true 的 .tscn。", "changed_files": []}


@dataclass
class SceneMouseFilterPassStrategy:
    strategy_id: str = "scene_mouse_filter_pass"

    def matches(self, issue: str) -> bool:
        raw = str(issue or "").strip()
        if not raw:
            return False
        low = raw.lower()
        if "mouse_filter" in low:
            return True
        if "鼠标" in raw and "过滤" in raw:
            return True
        return "挡住" in raw and "点击" in raw

    def diagnose(self, issue: str, verification: dict[str, Any]) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "summary": "疑似 Control.mouse_filter=STOP(0) 吞掉事件：尝试改为 PASS(2) 放行到子节点。",
            "checks": ["确认父节点 mouse_filter 是否误设为 STOP", "遮挡用的 ColorRect 是否 mouse_filter=IGNORE"],
            "issue_excerpt": str(issue or "").strip()[:500],
            "verification_hint": (verification.get("app_error") or {}).get("message")
            or verification.get("status")
            or "",
        }

    def apply_patch(self, project_root: Path, diagnosis: dict[str, Any]) -> dict[str, Any]:
        _ = diagnosis
        root = project_root.resolve()
        for tscn in sorted(root.rglob("*.tscn")):
            if ".godot" in tscn.parts:
                continue
            try:
                text = tscn.read_text(encoding="utf-8")
            except OSError:
                continue
            if "mouse_filter = 0" not in text:
                continue
            new_text, n = _TSCN_MOUSE_FILTER_ZERO.subn(r"\1mouse_filter = 2", text, count=1)
            if n != 1:
                continue
            try:
                tscn.write_text(new_text, encoding="utf-8")
            except OSError as exc:
                return {"applied": False, "reason": f"写入失败: {tscn}: {exc}", "changed_files": []}
            return {
                "applied": True,
                "changed_files": [str(tscn.resolve())],
                "notes": "已将首个 mouse_filter = 0 改为 2（Godot 4：PASS）。",
            }
        return {"applied": False, "reason": "未找到含 mouse_filter = 0 的 .tscn。", "changed_files": []}


@dataclass
class GdScriptParseErrorHintStrategy:
    strategy_id: str = "gdscript_parse_hint"

    def matches(self, issue: str) -> bool:
        raw = str(issue or "").strip()
        if not raw:
            return False
        low = raw.lower()
        if "parse error" in low or "解析错误" in raw:
            return True
        if "gdscript" in low and "error" in low:
            return True
        return bool(re.search(r"\(.*\d+,\s*\d+\)", raw))

    def diagnose(self, issue: str, verification: dict[str, Any]) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "summary": "疑似 GDScript 解析错误：请对照引擎报错行号修复语法；本策略仅写入提示文件，不自动改 .gd。",
            "checks": ["打开 Godot 输出/调试器查看首条 Parse Error 行号", "检查未闭合括号、缩进、拼写"],
            "issue_excerpt": str(issue or "").strip()[:500],
            "verification_hint": (verification.get("app_error") or {}).get("message")
            or verification.get("status")
            or "",
        }

    def apply_patch(self, project_root: Path, diagnosis: dict[str, Any]) -> dict[str, Any]:
        _ = diagnosis
        root = project_root.resolve()
        reports = root / "pointer_gpf" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        out = reports / "gpf_parse_error_hint.json"
        payload = {
            "strategy_id": self.strategy_id,
            "hint": "请根据引擎 Parse Error 定位 .gd 行号后手动修复语法；自动改写脚本风险过高。",
        }
        try:
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            return {"applied": False, "reason": f"写入失败: {out}: {exc}", "changed_files": []}
        return {
            "applied": True,
            "changed_files": [str(out.resolve())],
            "notes": "已写入解析错误排查提示（未修改脚本）。",
        }


@dataclass
class RuntimeBridgeAutoloadStrategy:
    strategy_id: str = "runtime_bridge_autoload"

    def matches(self, issue: str) -> bool:
        raw = str(issue or "").strip()
        if not raw:
            return False
        low = raw.lower().replace("_", "")
        if "pointergpfruntimebridge" in low or "runtimebridge" in low:
            return True
        if "runtime_bridge" in raw.lower():
            return True
        if "autoload" in low and "bridge" in low:
            return True
        if "timeout" in low and "bridge" in low:
            return True
        return False

    def diagnose(self, issue: str, verification: dict[str, Any]) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "summary": "疑似缺少 PointerGPF runtime bridge 自动加载项：尝试在 project.godot 写入 autoload 条目。",
            "checks": ["确认 addons/pointer_gpf/runtime_bridge.gd 存在", "确认 autoload 名称与路径与插件一致"],
            "issue_excerpt": str(issue or "").strip()[:500],
            "verification_hint": (verification.get("app_error") or {}).get("message")
            or verification.get("status")
            or "",
        }

    def apply_patch(self, project_root: Path, diagnosis: dict[str, Any]) -> dict[str, Any]:
        _ = diagnosis
        res = _ensure_pointer_gpf_runtime_autoload(project_root.resolve())
        if not res.get("ok"):
            return {
                "applied": False,
                "reason": str(res.get("reason", "autoload patch failed")),
                "changed_files": [],
            }
        changed = list(res.get("changed_files") or [])
        if not changed:
            return {
                "applied": False,
                "reason": "autoload 已存在且正确，未做修改。",
                "changed_files": [],
            }
        return {
            "applied": True,
            "changed_files": changed,
            "notes": f"已更新 project.godot autoload（{res.get('mode', '')}）。",
        }


DEFAULT_STRATEGIES: tuple[BugFixStrategy, ...] = (
    SignalDisconnectedHintStrategy(),
    SceneButtonDisabledFalseStrategy(),
    SceneMouseFilterPassStrategy(),
    GdScriptParseErrorHintStrategy(),
    RuntimeBridgeAutoloadStrategy(),
    ButtonNotClickableStrategy(),
)


def select_strategy(
    issue: str,
    strategies: tuple[BugFixStrategy, ...] | None = None,
    *,
    verification: dict[str, Any] | None = None,
) -> BugFixStrategy | None:
    haystack = _verification_augmented_issue(issue, verification)
    pool = strategies if strategies is not None else DEFAULT_STRATEGIES
    for s in pool:
        if s.matches(haystack):
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
    picked = select_strategy(issue, verification=verification)
    if picked is None:
        return default_diagnosis(issue, verification)
    return picked.diagnose(issue, verification)


def run_apply_patch(
    project_root: Path,
    issue: str,
    diagnosis: dict[str, Any],
    strategies: tuple[BugFixStrategy, ...] | None = None,
    *,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sid = str(diagnosis.get("strategy_id", "")).strip()
    pool = strategies if strategies is not None else DEFAULT_STRATEGIES
    for s in pool:
        if s.strategy_id == sid:
            return s.apply_patch(project_root, diagnosis)
    picked = select_strategy(issue, pool, verification=verification)
    if picked is None:
        return {
            "applied": False,
            "notes": "无可用策略执行补丁。",
        }
    return picked.apply_patch(project_root, diagnosis)
