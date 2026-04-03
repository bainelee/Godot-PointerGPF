#!/usr/bin/env python3
"""PointerGPF MCP server (CLI tool-style entry)."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SERVER_NAME = "pointer-gpf-mcp"
DEFAULT_SERVER_VERSION = "0.2.0"
DEFAULT_PLUGIN_ID = "pointer_gpf"
DEFAULT_PLUGIN_CFG_REL = f"addons/{DEFAULT_PLUGIN_ID}/plugin.cfg"
DEFAULT_CONTEXT_DIR_REL = "gameplayflow/project_context"
DEFAULT_SEED_FLOW_DIR_REL = "gameplayflow/generated_flows"
DEFAULT_SCAN_ROOTS = ["scripts", "scenes", "addons", "datas", "docs", "flows", "tests", "test", "src"]


class AppError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass
class ServerCtx:
    repo_root: Path
    template_plugin_dir: Path


@dataclass
class RuntimeConfig:
    server_name: str
    server_version: str
    plugin_id: str
    plugin_cfg_rel: str
    context_dir_rel: str
    index_rel: str
    seed_flow_dir_rel: str
    scan_roots: list[str]
    plugin_template_dir: Path
    config_sources: list[str]


@dataclass
class FileEntry:
    rel: str
    top: str
    suffix: str
    size: int
    mtime_ns: int

    def fingerprint(self) -> str:
        return f"{self.size}:{self.mtime_ns}"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_project_root(arguments: dict[str, Any]) -> Path:
    raw = str(arguments.get("project_root", "")).strip()
    if not raw:
        raise AppError("INVALID_ARGUMENT", "project_root is required")
    root = Path(raw).resolve()
    if not root.exists():
        raise AppError("INVALID_ARGUMENT", f"project_root not found: {root}")
    return root


def _default_runtime_config(ctx: ServerCtx) -> RuntimeConfig:
    return RuntimeConfig(
        server_name=DEFAULT_SERVER_NAME,
        server_version=DEFAULT_SERVER_VERSION,
        plugin_id=DEFAULT_PLUGIN_ID,
        plugin_cfg_rel=DEFAULT_PLUGIN_CFG_REL,
        context_dir_rel=DEFAULT_CONTEXT_DIR_REL,
        index_rel=f"{DEFAULT_CONTEXT_DIR_REL}/index.json",
        seed_flow_dir_rel=DEFAULT_SEED_FLOW_DIR_REL,
        scan_roots=list(DEFAULT_SCAN_ROOTS),
        plugin_template_dir=ctx.template_plugin_dir,
        config_sources=[],
    )


def _merge_runtime_config(base: RuntimeConfig, payload: dict[str, Any], source_label: str) -> RuntimeConfig:
    cfg = RuntimeConfig(
        server_name=base.server_name,
        server_version=base.server_version,
        plugin_id=base.plugin_id,
        plugin_cfg_rel=base.plugin_cfg_rel,
        context_dir_rel=base.context_dir_rel,
        index_rel=base.index_rel,
        seed_flow_dir_rel=base.seed_flow_dir_rel,
        scan_roots=list(base.scan_roots),
        plugin_template_dir=base.plugin_template_dir,
        config_sources=list(base.config_sources),
    )
    if not isinstance(payload, dict):
        return cfg
    if payload.get("server_name"):
        cfg.server_name = str(payload.get("server_name")).strip()
    if payload.get("server_version"):
        cfg.server_version = str(payload.get("server_version")).strip()
    if payload.get("plugin_id"):
        cfg.plugin_id = str(payload.get("plugin_id")).strip()
    if payload.get("plugin_cfg_rel"):
        cfg.plugin_cfg_rel = str(payload.get("plugin_cfg_rel")).replace("\\", "/").strip()
    if payload.get("context_dir_rel"):
        cfg.context_dir_rel = str(payload.get("context_dir_rel")).replace("\\", "/").strip()
        cfg.index_rel = f"{cfg.context_dir_rel}/index.json"
    if payload.get("index_rel"):
        cfg.index_rel = str(payload.get("index_rel")).replace("\\", "/").strip()
    if payload.get("seed_flow_dir_rel"):
        cfg.seed_flow_dir_rel = str(payload.get("seed_flow_dir_rel")).replace("\\", "/").strip()
    scan_roots = payload.get("scan_roots")
    if isinstance(scan_roots, list):
        normalized = [str(x).replace("\\", "/").strip() for x in scan_roots if str(x).strip()]
        if normalized:
            cfg.scan_roots = normalized
    tpl_rel = str(payload.get("plugin_template_dir_rel", "")).strip()
    if tpl_rel:
        cfg.plugin_template_dir = (base.plugin_template_dir.parents[2] / tpl_rel).resolve()
    if source_label not in cfg.config_sources:
        cfg.config_sources.append(source_label)
    return cfg


def _load_config_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AppError("CONFIG_READ_FAILED", f"failed to read config file: {path}", {"error": str(exc)}) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError("CONFIG_PARSE_FAILED", f"invalid json config file: {path}", {"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise AppError("CONFIG_INVALID", f"config file must be JSON object: {path}")
    return payload


def _resolve_runtime_config(ctx: ServerCtx, arguments: dict[str, Any], project_root: Path | None = None) -> RuntimeConfig:
    cfg = _default_runtime_config(ctx)
    repo_cfg = ctx.repo_root / "gtr.config.json"
    if repo_cfg.exists():
        cfg = _merge_runtime_config(cfg, _load_config_file(repo_cfg), str(repo_cfg))
    if project_root is None:
        project_root_raw = str(arguments.get("project_root", "")).strip()
        if project_root_raw:
            candidate = Path(project_root_raw).resolve()
            if candidate.exists():
                project_root = candidate
    if project_root is not None:
        project_cfg = project_root / "gtr.config.json"
        if project_cfg.exists():
            cfg = _merge_runtime_config(cfg, _load_config_file(project_cfg), str(project_cfg))
    config_file_raw = str(arguments.get("config_file", "")).strip()
    if config_file_raw:
        explicit_cfg = Path(config_file_raw).resolve()
        if not explicit_cfg.exists():
            raise AppError("CONFIG_NOT_FOUND", f"config_file not found: {explicit_cfg}")
        cfg = _merge_runtime_config(cfg, _load_config_file(explicit_cfg), str(explicit_cfg))
    return cfg


def _safe_read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _write_text(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise AppError("IO_ERROR", f"failed to write file: {path}", {"error": str(exc)}) from exc


def _ensure_plugin_enabled(project_root: Path, plugin_cfg_rel: str) -> dict[str, Any]:
    project_cfg = project_root / "project.godot"
    if not project_cfg.exists():
        raise AppError("PROJECT_GODOT_NOT_FOUND", f"missing file: {project_cfg}")
    text = _safe_read_text(project_cfg)
    target = f"res://{plugin_cfg_rel}"
    if "[editor_plugins]" not in text:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n[editor_plugins]\n"
        text += f'enabled=PackedStringArray("{target}")\n'
        _write_text(project_cfg, text)
        return {"enabled": True, "mode": "section_created"}
    lines = text.splitlines()
    section_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == "[editor_plugins]":
            section_idx = i
            break
    if section_idx < 0:
        raise AppError("INTERNAL_ERROR", "failed to locate [editor_plugins] section")
    key_idx = -1
    for i in range(section_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            break
        if stripped.startswith("enabled="):
            key_idx = i
            break
    if key_idx < 0:
        lines.insert(section_idx + 1, f'enabled=PackedStringArray("{target}")')
        _write_text(project_cfg, "\n".join(lines) + "\n")
        return {"enabled": True, "mode": "key_created"}
    current_line = lines[key_idx]
    if target in current_line:
        return {"enabled": True, "mode": "already_enabled"}
    prefix = "enabled=PackedStringArray("
    if current_line.strip().startswith(prefix) and current_line.strip().endswith(")"):
        inside = current_line.strip()[len(prefix) : -1].strip()
        new_inside = f'{inside}, "{target}"' if inside else f'"{target}"'
        lines[key_idx] = f"{prefix}{new_inside})"
    else:
        lines[key_idx] = f'enabled=PackedStringArray("{target}")'
    _write_text(project_cfg, "\n".join(lines) + "\n")
    return {"enabled": True, "mode": "key_updated"}


def _tool_install_godot_plugin(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    if not cfg.plugin_template_dir.exists():
        raise AppError("PLUGIN_TEMPLATE_NOT_FOUND", f"missing template dir: {cfg.plugin_template_dir}")
    target_dir = project_root / "addons" / cfg.plugin_id
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(cfg.plugin_template_dir, target_dir)
    enable_result = _ensure_plugin_enabled(project_root, cfg.plugin_cfg_rel)
    report = {
        "tool": "install_godot_plugin",
        "generated_at": _utc_iso(),
        "project_root": str(project_root),
        "plugin_target_dir": str(target_dir),
        "plugin_cfg": f"res://{cfg.plugin_cfg_rel}",
        "config_sources": cfg.config_sources,
        "enable_result": enable_result,
        "status": "installed",
    }
    report_path = project_root / "gameplayflow" / "plugin_install_report.json"
    _write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    report["report_path"] = str(report_path)
    return report


def _tool_enable_godot_plugin(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    plugin_cfg = project_root / cfg.plugin_cfg_rel
    if not plugin_cfg.exists():
        raise AppError(
            "PLUGIN_NOT_INSTALLED",
            "plugin files not found, run install_godot_plugin first",
            {"expected_plugin_cfg": str(plugin_cfg)},
        )
    enable_result = _ensure_plugin_enabled(project_root, cfg.plugin_cfg_rel)
    return {
        "tool": "enable_godot_plugin",
        "generated_at": _utc_iso(),
        "project_root": str(project_root),
        "plugin_cfg": f"res://{cfg.plugin_cfg_rel}",
        "config_sources": cfg.config_sources,
        "enable_result": enable_result,
        "status": "enabled",
    }


def _tool_update_godot_plugin(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    result = _tool_install_godot_plugin(ctx, arguments)
    result["tool"] = "update_godot_plugin"
    result["status"] = "updated"
    return result


def _tool_check_plugin_status(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    project_cfg = project_root / "project.godot"
    plugin_cfg = project_root / cfg.plugin_cfg_rel
    enabled = False
    if project_cfg.exists():
        content = _safe_read_text(project_cfg)
        enabled = f"res://{cfg.plugin_cfg_rel}" in content
    return {
        "project_root": str(project_root),
        "plugin_cfg_exists": plugin_cfg.exists(),
        "plugin_enabled_in_project_godot": enabled,
        "plugin_cfg": f"res://{cfg.plugin_cfg_rel}",
        "config_sources": cfg.config_sources,
        "status": "ready" if plugin_cfg.exists() and enabled else "not_ready",
    }


def _scan_files(project_root: Path, scan_roots: list[str], limit: int = 2500) -> list[FileEntry]:
    allow_roots = scan_roots or list(DEFAULT_SCAN_ROOTS)
    seen: set[str] = set()
    out: list[FileEntry] = []
    for root_name in allow_roots:
        base = project_root / root_name
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(project_root)).replace("\\", "/")
            if rel in seen:
                continue
            st = path.stat()
            out.append(
                FileEntry(
                    rel=rel,
                    top=rel.split("/", 1)[0],
                    suffix=path.suffix.lower(),
                    size=int(st.st_size),
                    mtime_ns=int(st.st_mtime_ns),
                )
            )
            seen.add(rel)
            if len(out) >= limit:
                return out
    for rel_name in ("project.godot", "README.md", "README.txt"):
        p = project_root / rel_name
        if not p.exists() or not p.is_file():
            continue
        rel = str(p.relative_to(project_root)).replace("\\", "/")
        if rel in seen:
            continue
        st = p.stat()
        out.append(
            FileEntry(
                rel=rel,
                top=rel.split("/", 1)[0],
                suffix=p.suffix.lower(),
                size=int(st.st_size),
                mtime_ns=int(st.st_mtime_ns),
            )
        )
    return sorted(out, key=lambda x: x.rel)


def _extract_project_name(project_root: Path) -> str:
    raw = _safe_read_text(project_root / "project.godot")
    match = re.search(r'config/name\s*=\s*"([^"]+)"', raw)
    return match.group(1).strip() if match else ""


def _extract_script_signals(project_root: Path, files: list[FileEntry], max_items: int = 50) -> dict[str, Any]:
    scripts = [f for f in files if f.suffix == ".gd"]
    classes: list[str] = []
    extends: list[str] = []
    methods: list[str] = []
    for entry in scripts[:200]:
        text = _safe_read_text(project_root / entry.rel)
        for c in re.findall(r"^\s*class_name\s+([A-Za-z0-9_]+)", text, flags=re.MULTILINE):
            if c not in classes:
                classes.append(c)
        for e in re.findall(r"^\s*extends\s+([A-Za-z0-9_\.]+)", text, flags=re.MULTILINE):
            if e not in extends:
                extends.append(e)
        for m in re.findall(r"^\s*func\s+([A-Za-z0-9_]+)\s*\(", text, flags=re.MULTILINE):
            if m not in methods:
                methods.append(m)
    return {
        "script_count": len(scripts),
        "class_names": classes[:max_items],
        "extends_types": extends[:max_items],
        "method_samples": methods[:max_items],
    }


def _extract_scene_signals(project_root: Path, files: list[FileEntry], max_items: int = 50) -> dict[str, Any]:
    scenes = [f for f in files if f.suffix == ".tscn"]
    roots: list[dict[str, str]] = []
    for entry in scenes[:200]:
        text = _safe_read_text(project_root / entry.rel)
        match = re.search(r'^\[node\s+name="([^"]+)"\s+type="([^"]+)"', text, flags=re.MULTILINE)
        if match:
            roots.append({"scene": entry.rel, "root_name": match.group(1), "root_type": match.group(2)})
        if len(roots) >= max_items:
            break
    return {"scene_count": len(scenes), "root_nodes": roots}


def _extract_data_signals(project_root: Path, files: list[FileEntry], max_files: int = 40) -> dict[str, Any]:
    json_files = [f for f in files if f.suffix == ".json" and f.top in {"datas", "data", "config"}]
    top_keys: dict[str, int] = {}
    parsed_files = 0
    for entry in json_files[:max_files]:
        raw = _safe_read_text(project_root / entry.rel)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        parsed_files += 1
        if isinstance(payload, dict):
            for key in payload.keys():
                skey = str(key)
                top_keys[skey] = top_keys.get(skey, 0) + 1
    ranked = sorted(top_keys.items(), key=lambda x: (-x[1], x[0]))
    return {
        "json_file_count": len(json_files),
        "json_parsed_count": parsed_files,
        "top_keys": [{"key": k, "freq": v} for k, v in ranked[:80]],
    }


def _derive_flow_candidates(
    script_signals: dict[str, Any],
    scene_signals: dict[str, Any],
    data_signals: dict[str, Any],
    inferred_keywords: list[str],
) -> dict[str, Any]:
    methods = [str(x) for x in script_signals.get("method_samples", []) if isinstance(x, str)]
    root_nodes = [x for x in scene_signals.get("root_nodes", []) if isinstance(x, dict)]
    data_keys = [str(x.get("key")) for x in data_signals.get("top_keys", []) if isinstance(x, dict)]

    actions: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    action_ids: set[str] = set()
    assertion_ids: set[str] = set()

    def push_action(action_id: str, kind: str, hint: str, evidence: list[str]) -> None:
        if action_id in action_ids:
            return
        action_ids.add(action_id)
        actions.append({"id": action_id, "kind": kind, "hint": hint, "evidence": evidence[:5]})

    def push_assert(assert_id: str, kind: str, hint: str, evidence: list[str]) -> None:
        if assert_id in assertion_ids:
            return
        assertion_ids.add(assert_id)
        assertions.append({"id": assert_id, "kind": kind, "hint": hint, "evidence": evidence[:5]})

    for method in methods:
        low = method.lower()
        if "pressed" in low or low.startswith("_on_"):
            push_action(
                f"action.click.{method}",
                "click",
                f"尝试通过按钮/交互信号触发 `{method}` 对应路径",
                [f"method:{method}"],
            )
        if "drag" in low or "move" in low or "camera" in low:
            push_action(
                f"action.drag.{method}",
                "drag",
                f"尝试基于 `{method}` 构造拖拽或移动操作",
                [f"method:{method}"],
            )
        if "wait" in low or "tick" in low or "process" in low:
            push_action(
                f"action.wait.{method}",
                "wait",
                f"可对 `{method}` 相关逻辑使用 wait/轮询推进",
                [f"method:{method}"],
            )
        if low.startswith("is_") or low.startswith("has_") or low.startswith("can_"):
            push_assert(
                f"assert.logic.{method}",
                "logic_state",
                f"把 `{method}` 映射为状态断言",
                [f"method:{method}"],
            )
        if "state" in low or "status" in low:
            push_assert(
                f"assert.state.{method}",
                "logic_state",
                f"优先检查 `{method}` 对应状态变化",
                [f"method:{method}"],
            )

    for root in root_nodes[:40]:
        scene = str(root.get("scene", ""))
        rname = str(root.get("root_name", ""))
        rtype = str(root.get("root_type", ""))
        if "Control" in rtype or "Panel" in rtype:
            push_action(
                f"action.open_ui.{rname}",
                "click",
                f"进入 `{scene}` 后验证 UI 根节点 `{rname}` 可见/可交互",
                [f"scene:{scene}", f"root:{rname}", f"type:{rtype}"],
            )
            push_assert(
                f"assert.ui.visible.{rname}",
                "visual_hard",
                f"检查 `{rname}` 的可见性与布局稳定性",
                [f"scene:{scene}", f"type:{rtype}"],
            )
        if "Node2D" in rtype or "Node3D" in rtype:
            push_action(
                f"action.enter_scene.{rname}",
                "wait",
                f"进入 `{scene}` 后等待 `{rname}` 场景树稳定",
                [f"scene:{scene}", f"type:{rtype}"],
            )

    for key in data_keys[:40]:
        low = key.lower()
        if any(x in low for x in ("resource", "currency", "value", "stats", "factor")):
            push_assert(
                f"assert.data.{key}",
                "logic_state",
                f"构造资源/数值断言，重点跟踪 `{key}`",
                [f"data_key:{key}"],
            )
        if any(x in low for x in ("room", "map", "region", "explore")):
            push_action(
                f"action.progress.{key}",
                "wait",
                f"围绕 `{key}` 构造推进与解锁流程",
                [f"data_key:{key}"],
            )

    if "ui-heavy" in inferred_keywords:
        push_assert(
            "assert.ui.snapshot.baseline",
            "visual_hard",
            "该项目偏 UI 驱动，建议默认启用截图/布局基线断言",
            ["keyword:ui-heavy"],
        )
    if "exploration" in inferred_keywords:
        push_action(
            "action.explore.region_cycle",
            "wait",
            "检测到探索关键词，建议加入 region/map 轮转流程",
            ["keyword:exploration"],
        )
    if "builder" in inferred_keywords:
        push_action(
            "action.builder.build_cycle",
            "wait",
            "检测到建造关键词，建议覆盖 build->wait->verify 完整闭环",
            ["keyword:builder"],
        )

    return {
        "action_candidates": actions[:120],
        "assertion_candidates": assertions[:120],
    }


def _flow_candidates_markdown(flow_candidates: dict[str, Any]) -> str:
    actions = [x for x in flow_candidates.get("action_candidates", []) if isinstance(x, dict)]
    assertions = [x for x in flow_candidates.get("assertion_candidates", []) if isinstance(x, dict)]
    parts: list[str] = [
        "# Flow Candidate Catalog",
        "",
        "## Action Candidates",
        "",
    ]
    if actions:
        parts.extend(
            [
                f"- `{item.get('id')}` ({item.get('kind')}): {item.get('hint')}"
                for item in actions[:80]
                if isinstance(item.get("id"), str)
            ]
        )
    else:
        parts.append("- none")
    parts.extend(["", "## Assertion Candidates", ""])
    if assertions:
        parts.extend(
            [
                f"- `{item.get('id')}` ({item.get('kind')}): {item.get('hint')}"
                for item in assertions[:80]
                if isinstance(item.get("id"), str)
            ]
        )
    else:
        parts.append("- none")
    return "\n".join(parts) + "\n"


def _extract_todo_signals(project_root: Path, files: list[FileEntry], max_items: int = 80) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    markers = ("TODO", "FIXME", "待办", "待處理", "待处理")
    for entry in files:
        if entry.suffix not in (".md", ".gd", ".json", ".txt", ".tscn", ".cfg", ".py"):
            continue
        text = _safe_read_text(project_root / entry.rel)
        if not text:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            if any(marker in line for marker in markers):
                hits.append({"file": entry.rel, "line": idx, "text": line.strip()[:220]})
                if len(hits) >= max_items:
                    return hits
    return hits


def _infer_keywords(files: list[FileEntry]) -> list[str]:
    corpus = " ".join(entry.rel.lower() for entry in files)
    mapping = {
        "rpg": ("battle", "quest", "inventory", "skill"),
        "builder": ("build", "construction", "room", "base"),
        "exploration": ("explore", "region", "map", "investigation"),
        "simulation": ("sim", "tick", "economy", "resource"),
        "ui-heavy": ("ui", "panel", "overlay", "layout"),
    }
    out: list[str] = []
    for key, words in mapping.items():
        if any(w in corpus for w in words):
            out.append(key)
    return out


def _context_unknowns(project_root: Path) -> list[str]:
    missing: list[str] = []
    if not (project_root / "project.godot").exists():
        missing.append("project.godot missing; runtime contract unknown")
    if not (project_root / "scenes").exists():
        missing.append("scenes/ not found; scene entrypoints unknown")
    if not (project_root / "scripts").exists():
        missing.append("scripts/ not found; gameplay logic modules unknown")
    if not (project_root / "flows").exists():
        missing.append("flows/ not found; flow templates unavailable")
    return missing


def _confidence_score(files: list[FileEntry], unknowns: list[str]) -> float:
    score = 0.3
    tops = {f.top for f in files}
    if "project.godot" in {f.rel for f in files}:
        score += 0.2
    if "scripts" in tops:
        score += 0.2
    if "scenes" in tops:
        score += 0.15
    if "datas" in tops or "data" in tops:
        score += 0.1
    if "docs" in tops:
        score += 0.05
    score -= min(0.25, 0.05 * len(unknowns))
    return round(max(0.05, min(0.99, score)), 2)


def _load_previous_index(project_root: Path, index_rel: str) -> dict[str, Any]:
    path = project_root / index_rel
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_context_index_or_fail(project_root: Path, index_rel: str) -> dict[str, Any]:
    path = project_root / index_rel
    if not path.exists():
        raise AppError(
            "CONTEXT_INDEX_NOT_FOUND",
            "missing project context index; run init_project_context first",
            {"expected_index": str(path)},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError("CONTEXT_INDEX_INVALID", "failed to parse context index", {"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise AppError("CONTEXT_INDEX_INVALID", "context index must be a JSON object")
    return payload


def _slugify(text: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_]+", "_", str(text).strip())
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw.lower() or "flow_seed"


def _compute_delta(previous: dict[str, Any], files: list[FileEntry]) -> dict[str, Any]:
    prev_map = previous.get("file_fingerprints", {}) if isinstance(previous.get("file_fingerprints"), dict) else {}
    current_map = {f.rel: f.fingerprint() for f in files}
    prev_keys = set(prev_map.keys())
    cur_keys = set(current_map.keys())
    added = sorted(cur_keys - prev_keys)
    removed = sorted(prev_keys - cur_keys)
    changed = sorted([k for k in (cur_keys & prev_keys) if str(prev_map.get(k)) != str(current_map.get(k))])
    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added_samples": added[:25],
        "removed_samples": removed[:25],
        "changed_samples": changed[:25],
        "has_delta": bool(added or removed or changed),
    }


def _build_context_docs(
    project_root: Path,
    files: list[FileEntry],
    previous: dict[str, Any],
    cfg: RuntimeConfig,
) -> dict[str, Any]:
    generated_at = _utc_iso()
    context_dir = project_root / cfg.context_dir_rel
    by_prefix: dict[str, int] = {}
    by_suffix: dict[str, int] = {}
    for rel in files:
        by_prefix[rel.top] = by_prefix.get(rel.top, 0) + 1
        by_suffix[rel.suffix or "<none>"] = by_suffix.get(rel.suffix or "<none>", 0) + 1
    unknowns = _context_unknowns(project_root)
    confidence = _confidence_score(files, unknowns)
    project_name = _extract_project_name(project_root) or "(unknown)"
    script_signals = _extract_script_signals(project_root, files)
    scene_signals = _extract_scene_signals(project_root, files)
    data_signals = _extract_data_signals(project_root, files)
    todo_signals = _extract_todo_signals(project_root, files)
    keywords = _infer_keywords(files)
    flow_candidates = _derive_flow_candidates(
        script_signals=script_signals,
        scene_signals=scene_signals,
        data_signals=data_signals,
        inferred_keywords=keywords,
    )
    delta = _compute_delta(previous, files)

    overview = (
        "# Project Overview\n\n"
        f"- generated_at: {generated_at}\n"
        f"- project_root: {project_root}\n"
        f"- project_name: {project_name}\n"
        f"- scanned_files: {len(files)}\n"
        f"- confidence: {confidence}\n\n"
        "## Top-Level Coverage\n\n"
        + "\n".join(f"- `{k}`: {v}" for k, v in sorted(by_prefix.items()))
        + "\n\n## Inferred Keywords\n\n"
        + ("\n".join(f"- `{k}`" for k in keywords) if keywords else "- `unknown`")
        + "\n\n## Unknowns\n\n"
        + ("\n".join(f"- {u}" for u in unknowns) if unknowns else "- none")
        + "\n"
    )
    runtime_arch = (
        "# Runtime Architecture\n\n"
        f"- generated_at: {generated_at}\n"
        f"- script_count: {script_signals['script_count']}\n"
        f"- scene_count: {scene_signals['scene_count']}\n\n"
        "## Script Class Signals\n\n"
        + ("\n".join(f"- `{x}`" for x in script_signals["class_names"]) if script_signals["class_names"] else "- none")
        + "\n\n## Scene Root Signals\n\n"
        + (
            "\n".join(
                f"- `{x['scene']}` => `{x['root_name']}` (`{x['root_type']}`)" for x in scene_signals["root_nodes"]
            )
            if scene_signals["root_nodes"]
            else "- none"
        )
        + "\n"
    )
    test_surface = (
        "# Test Surface\n\n"
        f"- generated_at: {generated_at}\n\n"
        "## Candidate Hooks\n\n"
        f"- scripts: {script_signals['script_count']}\n"
        f"- scenes: {scene_signals['scene_count']}\n"
        f"- docs: {by_prefix.get('docs', 0)}\n"
        f"- flows: {by_prefix.get('flows', 0)}\n\n"
        "## TODO / FIXME Signals\n\n"
        + (
            "\n".join(f"- `{x['file']}`:{x['line']} {x['text']}" for x in todo_signals[:30])
            if todo_signals
            else "- none"
        )
        + "\n"
    )
    flow_guide = (
        "# Flow Authoring Guide\n\n"
        f"- generated_at: {generated_at}\n"
        f"- confidence: {confidence}\n\n"
        "## Rules\n\n"
        "- Prefer explicit action and verify pairs.\n"
        "- Use scene and script signals from `index.json` to pick stable targets.\n"
        "- If confidence < 0.6, generate conservative smoke flows first.\n"
        "- After major refactor, call `refresh_project_context` before generating new flows.\n\n"
        "## Refresh Delta\n\n"
        f"- added: {delta['added_count']}\n"
        f"- removed: {delta['removed_count']}\n"
        f"- changed: {delta['changed_count']}\n"
    )
    flow_catalog = _flow_candidates_markdown(flow_candidates)

    fingerprints = {f.rel: f.fingerprint() for f in files}
    index = {
        "generated_at": generated_at,
        "project_root": str(project_root),
        "project_name": project_name,
        "confidence": confidence,
        "unknowns": unknowns,
        "source_paths": sorted({f.top for f in files}),
        "source_counts": by_prefix,
        "suffix_counts": by_suffix,
        "inferred_keywords": keywords,
        "delta": delta,
        "script_signals": script_signals,
        "scene_signals": scene_signals,
        "data_signals": data_signals,
        "flow_candidates": flow_candidates,
        "todo_signals": todo_signals[:80],
        "documents": {
            "overview": "01-project-overview.md",
            "runtime_architecture": "02-runtime-architecture.md",
            "test_surface": "03-test-surface.md",
            "flow_authoring_guide": "04-flow-authoring-guide.md",
            "flow_candidate_catalog": "05-flow-candidate-catalog.md",
        },
        "config_sources": cfg.config_sources,
        "effective_config": {
            "plugin_id": cfg.plugin_id,
            "plugin_cfg_rel": cfg.plugin_cfg_rel,
            "context_dir_rel": cfg.context_dir_rel,
            "index_rel": cfg.index_rel,
            "seed_flow_dir_rel": cfg.seed_flow_dir_rel,
            "scan_roots": cfg.scan_roots,
            "plugin_template_dir": str(cfg.plugin_template_dir),
        },
        "file_fingerprints": fingerprints,
    }
    _write_text(context_dir / "01-project-overview.md", overview)
    _write_text(context_dir / "02-runtime-architecture.md", runtime_arch)
    _write_text(context_dir / "03-test-surface.md", test_surface)
    _write_text(context_dir / "04-flow-authoring-guide.md", flow_guide)
    _write_text(context_dir / "05-flow-candidate-catalog.md", flow_catalog)
    _write_text(context_dir / "index.json", json.dumps(index, ensure_ascii=False, indent=2))
    return {
        "documents": {
            "context_dir": str(context_dir),
            "overview": str(context_dir / "01-project-overview.md"),
            "runtime_architecture": str(context_dir / "02-runtime-architecture.md"),
            "test_surface": str(context_dir / "03-test-surface.md"),
            "flow_authoring_guide": str(context_dir / "04-flow-authoring-guide.md"),
            "flow_candidate_catalog": str(context_dir / "05-flow-candidate-catalog.md"),
            "index_json": str(context_dir / "index.json"),
        },
        "index": index,
    }


def _run_project_context_generation(ctx: ServerCtx, arguments: dict[str, Any], mode: str) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    max_files = int(arguments.get("max_files", 2500))
    if max_files <= 0:
        raise AppError("INVALID_ARGUMENT", "max_files must be > 0")
    files = _scan_files(project_root=project_root, scan_roots=cfg.scan_roots, limit=max_files)
    previous = _load_previous_index(project_root, cfg.index_rel)
    built = _build_context_docs(project_root=project_root, files=files, previous=previous, cfg=cfg)
    index = built["index"]
    return {
        "status": mode,
        "project_root": str(project_root),
        "files_scanned_count": len(files),
        "confidence": index["confidence"],
        "unknowns": index["unknowns"],
        "delta": index["delta"],
        "flow_candidates_summary": {
            "action_count": len(index.get("flow_candidates", {}).get("action_candidates", [])),
            "assertion_count": len(index.get("flow_candidates", {}).get("assertion_candidates", [])),
        },
        "config_sources": cfg.config_sources,
        "documents": built["documents"],
    }


def _pick_seed_strategy(arguments: dict[str, Any], context_index: dict[str, Any]) -> str:
    allowed = {"auto", "ui", "exploration", "builder", "generic"}
    requested = str(arguments.get("strategy", "auto")).strip().lower() or "auto"
    if requested not in allowed:
        raise AppError("INVALID_ARGUMENT", f"unsupported strategy: {requested}", {"allowed": sorted(allowed)})
    if requested != "auto":
        return requested
    keywords = [
        str(x).strip().lower()
        for x in context_index.get("inferred_keywords", [])
        if isinstance(x, str) and str(x).strip()
    ]
    if "ui-heavy" in keywords:
        return "ui"
    if "exploration" in keywords:
        return "exploration"
    if "builder" in keywords:
        return "builder"
    return "generic"


def _candidate_action_step(step_id: str, candidate: dict[str, Any], fallback_action: str) -> dict[str, Any]:
    return {
        "id": step_id,
        "action": str(candidate.get("kind", fallback_action) or fallback_action),
        "candidate_id": str(candidate.get("id", "")),
        "hint": str(candidate.get("hint", "")),
    }


def _candidate_assert_step(step_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": step_id,
        "action": "check",
        "kind": str(candidate.get("kind", "logic_state")),
        "candidate_id": str(candidate.get("id", "")),
        "hint": str(candidate.get("hint", "")),
    }


def _seed_steps_by_strategy(
    strategy: str,
    action_candidates: list[dict[str, Any]],
    assertion_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = [f"seed_strategy={strategy}"]
    steps: list[dict[str, Any]] = [
        {"id": "launch_game", "action": "launchGame"},
        {"id": "wait_bootstrap", "action": "wait", "until": {"hint": "main_scene_ready"}, "timeoutMs": 15000},
    ]

    def action_at(index: int) -> dict[str, Any]:
        if index < len(action_candidates):
            return action_candidates[index]
        return {}

    def assert_at(index: int) -> dict[str, Any]:
        if index < len(assertion_candidates):
            return assertion_candidates[index]
        return {}

    if strategy == "ui":
        steps.append({"id": "open_ui_panel", "action": "click", "target": {"hint": "open_main_ui_panel"}})
        c0 = action_at(0)
        if c0:
            steps.append(_candidate_action_step("ui_candidate_action_1", c0, "click"))
        a0 = assert_at(0)
        if a0:
            steps.append(_candidate_assert_step("ui_assert_layout_1", a0))
        else:
            steps.append(
                {"id": "ui_assert_layout_1", "action": "check", "kind": "visual_hard", "hint": "verify ui layout"}
            )
        steps.append({"id": "snapshot_ui", "action": "snapshot", "name": "ui_state"})
        notes.append("ui-first seed: focus on panel open and visual check")
    elif strategy == "exploration":
        steps.append({"id": "enter_map", "action": "click", "target": {"hint": "open_map_or_region"}})
        c0 = action_at(0)
        if c0:
            steps.append(_candidate_action_step("explore_candidate_action_1", c0, "wait"))
        steps.append({"id": "wait_explore_tick", "action": "wait", "until": {"hint": "exploration_progress"}, "timeoutMs": 30000})
        a0 = assert_at(0)
        if a0:
            steps.append(_candidate_assert_step("explore_assert_state_1", a0))
        else:
            steps.append(
                {"id": "explore_assert_state_1", "action": "check", "kind": "logic_state", "hint": "verify explore state"}
            )
        steps.append({"id": "snapshot_explore", "action": "snapshot", "name": "explore_state"})
        notes.append("exploration seed: focus on map entry, wait, and progress assert")
    elif strategy == "builder":
        steps.append({"id": "open_build_mode", "action": "click", "target": {"hint": "open_build_ui"}})
        c0 = action_at(0)
        if c0:
            steps.append(_candidate_action_step("build_candidate_action_1", c0, "click"))
        steps.append({"id": "wait_build_complete", "action": "wait", "until": {"hint": "build_complete"}, "timeoutMs": 45000})
        a0 = assert_at(0)
        if a0:
            steps.append(_candidate_assert_step("build_assert_state_1", a0))
        else:
            steps.append(
                {"id": "build_assert_state_1", "action": "check", "kind": "logic_state", "hint": "verify build result"}
            )
        steps.append({"id": "snapshot_build", "action": "snapshot", "name": "build_state"})
        notes.append("builder seed: focus on build lifecycle and completion assert")
    else:
        c0 = action_at(0)
        c1 = action_at(1)
        if c0:
            steps.append(_candidate_action_step("candidate_action_1", c0, "click"))
        if c1:
            steps.append(_candidate_action_step("candidate_action_2", c1, "wait"))
        a0 = assert_at(0)
        if a0:
            steps.append(_candidate_assert_step("candidate_assert_1", a0))
        else:
            steps.append(
                {"id": "candidate_assert_1", "action": "check", "kind": "logic_state", "hint": "verify core state"}
            )
        steps.append({"id": "snapshot_generic", "action": "snapshot", "name": "seed_end"})
        notes.append("generic seed: use top candidates directly")

    steps.append({"id": "snapshot_end", "action": "snapshot", "name": "seed_end"})
    return steps, notes


def _step_chat_hint(step: dict[str, Any]) -> dict[str, Any]:
    action = str(step.get("action", "")).strip().lower()
    if action == "check":
        result_hint = "assertion executed"
        verify_hint = "assertion passed or failure reason recorded"
    elif action == "wait":
        result_hint = "wait window completed"
        verify_hint = "target condition reached or timeout handled"
    elif action == "snapshot":
        result_hint = "snapshot captured"
        verify_hint = "artifact path recorded"
    else:
        result_hint = "action executed"
        verify_hint = "state transition validated"
    return {
        "required_phases": ["started", "result", "verify"],
        "started_hint": f"step `{step.get('id', '')}` started",
        "result_hint": result_hint,
        "verify_hint": verify_hint,
    }


def _attach_chat_contract(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in steps:
        row = dict(step)
        row["chat_contract"] = _step_chat_hint(step)
        out.append(row)
    return out


def _tool_generate_flow_seed(_ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(_ctx, arguments, project_root=project_root)
    context_index = _load_context_index_or_fail(project_root, cfg.index_rel)
    flow_id_raw = str(arguments.get("flow_id", "")).strip() or f"seed_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    flow_id = _slugify(flow_id_raw)
    flow_name = str(arguments.get("flow_name", "")).strip() or "Auto generated flow seed"
    candidates = context_index.get("flow_candidates", {}) if isinstance(context_index.get("flow_candidates"), dict) else {}
    action_candidates = [
        x for x in candidates.get("action_candidates", []) if isinstance(x, dict) and str(x.get("id", "")).strip()
    ]
    assertion_candidates = [
        x for x in candidates.get("assertion_candidates", []) if isinstance(x, dict) and str(x.get("id", "")).strip()
    ]
    strategy = _pick_seed_strategy(arguments, context_index)
    steps, strategy_notes = _seed_steps_by_strategy(
        strategy=strategy,
        action_candidates=action_candidates,
        assertion_candidates=assertion_candidates,
    )
    seeded_steps = _attach_chat_contract(steps)

    payload = {
        "flowId": flow_id,
        "name": flow_name,
        "seed_strategy": strategy,
        "chat_protocol_mode": "three_phase",
        "chat_contract_version": "v1",
        "generated_by": cfg.server_name,
        "generated_at": _utc_iso(),
        "source_context_index": cfg.index_rel,
        "steps": seeded_steps,
        "notes": [
            "This is a generated seed. Replace hints with concrete targets.",
            "Run refresh_project_context after major project changes.",
            "Each step includes chat_contract for started/result/verify compatibility.",
        ]
        + strategy_notes,
    }

    output_raw = str(arguments.get("output_file", "")).strip()
    if output_raw:
        output_path = Path(output_raw).resolve()
    else:
        output_path = (project_root / cfg.seed_flow_dir_rel / f"{flow_id}.json").resolve()
    _write_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return {
        "status": "generated",
        "project_root": str(project_root),
        "flow_id": flow_id,
        "flow_file": str(output_path),
        "seed_strategy": strategy,
        "step_count": len(seeded_steps),
        "from_action_candidates": len(action_candidates),
        "from_assertion_candidates": len(assertion_candidates),
    }


def _tool_get_adapter_contract(ctx: ServerCtx, _arguments: dict[str, Any]) -> dict[str, Any]:
    contract_path = ctx.repo_root / "mcp" / "adapter_contract_v1.json"
    if not contract_path.exists():
        raise AppError("CONTRACT_NOT_FOUND", f"adapter contract file not found: {contract_path}")
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError("CONTRACT_INVALID", "adapter contract json invalid", {"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise AppError("CONTRACT_INVALID", "adapter contract must be JSON object")
    payload["source_file"] = str(contract_path)
    return payload


def _tool_init_project_context(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    return _run_project_context_generation(ctx, arguments, mode="initialized")


def _tool_refresh_project_context(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    return _run_project_context_generation(ctx, arguments, mode="refreshed")


def _tool_get_mcp_runtime_info(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    cfg = _resolve_runtime_config(ctx, arguments)
    return {
        "server_name": cfg.server_name,
        "server_version": cfg.server_version,
        "repo_root": str(ctx.repo_root),
        "plugin_template_dir": str(cfg.plugin_template_dir),
        "context_output_dir": cfg.context_dir_rel,
        "seed_flow_output_dir": cfg.seed_flow_dir_rel,
        "config_sources": cfg.config_sources,
        "tools": [
            "get_mcp_runtime_info",
            "get_adapter_contract",
            "install_godot_plugin",
            "enable_godot_plugin",
            "update_godot_plugin",
            "check_plugin_status",
            "init_project_context",
            "refresh_project_context",
            "generate_flow_seed",
        ],
    }


def _build_tool_map() -> dict[str, Any]:
    return {
        "get_mcp_runtime_info": _tool_get_mcp_runtime_info,
        "get_adapter_contract": _tool_get_adapter_contract,
        "install_godot_plugin": _tool_install_godot_plugin,
        "enable_godot_plugin": _tool_enable_godot_plugin,
        "update_godot_plugin": _tool_update_godot_plugin,
        "check_plugin_status": _tool_check_plugin_status,
        "init_project_context": _tool_init_project_context,
        "refresh_project_context": _tool_refresh_project_context,
        "generate_flow_seed": _tool_generate_flow_seed,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PointerGPF MCP server")
    parser.add_argument("--tool", required=True, help="Tool name")
    parser.add_argument("--args", default="{}", help="JSON args object")
    parser.add_argument("--config-file", default=None, help="Explicit runtime config JSON file path")
    parser.add_argument("--project-root", default=None, help="Shortcut for project_root")
    parser.add_argument("--max-files", type=int, default=None, help="Shortcut for max_files")
    parser.add_argument("--flow-id", default=None, help="Shortcut for flow_id")
    parser.add_argument("--flow-name", default=None, help="Shortcut for flow_name")
    parser.add_argument("--output-file", default=None, help="Shortcut for output_file")
    parser.add_argument("--strategy", default=None, help="Shortcut for seed strategy (auto/ui/exploration/builder/generic)")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    ctx = ServerCtx(
        repo_root=repo_root,
        template_plugin_dir=repo_root / "godot_plugin_template" / "addons" / DEFAULT_PLUGIN_ID,
    )
    tool_map = _build_tool_map()
    try:
        payload = json.loads(args.args)
        if not isinstance(payload, dict):
            raise AppError("INVALID_ARGUMENT", "args must be a JSON object")
        if args.project_root is not None:
            payload["project_root"] = args.project_root
        if args.config_file is not None:
            payload["config_file"] = args.config_file
        if args.max_files is not None:
            payload["max_files"] = int(args.max_files)
        if args.flow_id is not None:
            payload["flow_id"] = args.flow_id
        if args.flow_name is not None:
            payload["flow_name"] = args.flow_name
        if args.output_file is not None:
            payload["output_file"] = args.output_file
        if args.strategy is not None:
            payload["strategy"] = args.strategy
        handler = tool_map.get(args.tool)
        if handler is None:
            raise AppError("UNSUPPORTED_TOOL", f"unsupported tool: {args.tool}")
        result = handler(ctx, payload)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except AppError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        print(json.dumps({"ok": False, "error": {"code": "INTERNAL_ERROR", "message": str(exc)}}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
