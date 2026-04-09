#!/usr/bin/env python3
"""PointerGPF MCP server (CLI tool-style entry)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flow_execution import FlowExecutionStepFailed, FlowExecutionTimeout, FlowRunOptions, FlowRunner


DEFAULT_SERVER_NAME = "pointer-gpf-mcp"
DEFAULT_SERVER_VERSION = "0.2.4.3"
DEFAULT_PLUGIN_ID = "pointer_gpf"
DEFAULT_PLUGIN_CFG_REL = f"addons/{DEFAULT_PLUGIN_ID}/plugin.cfg"
DEFAULT_WORKSPACE_DIR_REL = "pointer_gpf"
DEFAULT_CONTEXT_DIR_REL = f"{DEFAULT_WORKSPACE_DIR_REL}/project_context"
DEFAULT_SEED_FLOW_DIR_REL = f"{DEFAULT_WORKSPACE_DIR_REL}/generated_flows"
DEFAULT_REPORT_DIR_REL = f"{DEFAULT_WORKSPACE_DIR_REL}/reports"
DEFAULT_EXP_DIR_REL = f"{DEFAULT_WORKSPACE_DIR_REL}/gpf-exp"
DEFAULT_SCAN_ROOTS = ["scripts", "scenes", "addons", "datas", "docs", "flows", "tests", "test", "src"]
_MCP_IO_MODE = "header"


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
    report_dir_rel: str
    exp_dir_rel: str
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
        report_dir_rel=DEFAULT_REPORT_DIR_REL,
        exp_dir_rel=DEFAULT_EXP_DIR_REL,
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
        report_dir_rel=base.report_dir_rel,
        exp_dir_rel=base.exp_dir_rel,
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
    if payload.get("report_dir_rel"):
        cfg.report_dir_rel = str(payload.get("report_dir_rel")).replace("\\", "/").strip()
    if payload.get("exp_dir_rel"):
        cfg.exp_dir_rel = str(payload.get("exp_dir_rel")).replace("\\", "/").strip()
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


def _append_text(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:
        raise AppError("IO_ERROR", f"failed to append file: {path}", {"error": str(exc)}) from exc


def _exp_runtime_dir(project_root: Path, cfg: RuntimeConfig) -> Path:
    return (project_root / cfg.exp_dir_rel / "runtime").resolve()


def _legacy_layout_hints(project_root: Path) -> list[dict[str, str]]:
    candidates = [
        ("gameplayflow/project_context", "legacy_project_context"),
        ("gameplayflow/generated_flows", "legacy_generated_flows"),
        ("gpf-exp", "legacy_exp_root"),
    ]
    out: list[dict[str, str]] = []
    for rel, kind in candidates:
        p = project_root / rel
        if p.exists():
            out.append(
                {
                    "kind": kind,
                    "path": str(p),
                    "message": f"legacy path detected: {rel}. Run scripts/migrate-legacy-layout.ps1 to migrate into pointer_gpf/",
                }
            )
    return out


def _write_exp_runtime_artifact(
    project_root: Path,
    cfg: RuntimeConfig,
    artifact_name: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    runtime_dir = _exp_runtime_dir(project_root, cfg)
    slug = _slugify(artifact_name) or "runtime_artifact"
    artifact_path = runtime_dir / f"{slug}.json"
    _write_text(artifact_path, json.dumps(payload, ensure_ascii=False, indent=2))
    event_path = runtime_dir / "events.ndjson"
    _append_text(event_path, json.dumps(payload, ensure_ascii=False) + "\n")
    return {
        "exp_output_dir": str((project_root / cfg.exp_dir_rel).resolve()),
        "exp_runtime_dir": str(runtime_dir),
        "artifact_file": str(artifact_path),
        "event_log_file": str(event_path),
    }


def _resolve_existing_file(raw: str, field_name: str) -> Path:
    path = Path(str(raw).strip()).resolve()
    if not str(raw).strip():
        raise AppError("INVALID_ARGUMENT", f"{field_name} is required")
    if not path.exists() or not path.is_file():
        raise AppError("INVALID_ARGUMENT", f"{field_name} not found: {path}")
    return path


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError("INVALID_ARGUMENT", f"invalid json file: {path}", {"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise AppError("INVALID_ARGUMENT", f"json file must contain object: {path}")
    return payload


def _is_png_file(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(8) == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False


def _convert_image_to_png_if_needed(source: Path, target_png: Path) -> Path:
    if _is_png_file(source):
        if source.resolve() != target_png.resolve():
            shutil.copyfile(source, target_png)
        return target_png
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pylint: disable=broad-except
        raise AppError(
            "INVALID_ARGUMENT",
            "figma_screenshot_file is not a valid PNG; install Pillow or provide PNG input",
            {"file": str(source), "error": str(exc)},
        ) from exc
    try:
        img = Image.open(source)
        img.save(target_png, format="PNG")
    except Exception as exc:  # pylint: disable=broad-except
        raise AppError("INVALID_ARGUMENT", "failed to convert baseline image to PNG", {"error": str(exc)}) from exc
    return target_png


def _byte_diff_ratio(left: bytes, right: bytes) -> float:
    if not left and not right:
        return 0.0
    max_len = max(len(left), len(right))
    total = abs(len(left) - len(right)) * 255
    common = min(len(left), len(right))
    for idx in range(common):
        total += abs(left[idx] - right[idx])
    return round(total / (max_len * 255), 6)


def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_png_scanlines(payload: bytes, width: int, height: int, bytes_per_pixel: int) -> bytes:
    stride = width * bytes_per_pixel
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        if pos >= len(payload):
            break
        filter_type = payload[pos]
        pos += 1
        if pos + stride > len(payload):
            break
        row = bytearray(payload[pos : pos + stride])
        pos += stride
        if filter_type == 1:
            for i in range(stride):
                left = row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                row[i] = (row[i] + left) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                up = prev[i]
                row[i] = (row[i] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                left = row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                up = prev[i]
                up_left = prev[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                row[i] = (row[i] + _paeth_predictor(left, up, up_left)) & 0xFF
        out.extend(row)
        prev = row
    return bytes(out)


def _parse_png_metrics(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    signature = b"\x89PNG\r\n\x1a\n"
    if len(raw) < 8 or raw[:8] != signature:
        return {"format": "unknown", "width": 0, "height": 0, "raw_payload": b"", "byte_size": len(raw)}
    offset = 8
    width = 0
    height = 0
    bit_depth = 0
    color_type = 0
    idat_parts: list[bytes] = []
    while offset + 8 <= len(raw):
        chunk_len = struct.unpack(">I", raw[offset : offset + 4])[0]
        chunk_type = raw[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + chunk_len
        crc_end = data_end + 4
        if crc_end > len(raw):
            break
        chunk_data = raw[data_start:data_end]
        if chunk_type == b"IHDR" and len(chunk_data) >= 13:
            width = struct.unpack(">I", chunk_data[0:4])[0]
            height = struct.unpack(">I", chunk_data[4:8])[0]
            bit_depth = int(chunk_data[8])
            color_type = int(chunk_data[9])
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            break
        offset = crc_end
    decompressed = b""
    if idat_parts:
        try:
            decompressed = zlib.decompress(b"".join(idat_parts))
        except zlib.error:
            decompressed = b""
    pixel_data = b""
    channels_map = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    channels = channels_map.get(color_type, 0)
    if decompressed and width > 0 and height > 0 and bit_depth == 8 and channels > 0:
        pixel_data = _unfilter_png_scanlines(decompressed, width, height, channels)
    return {
        "format": "png",
        "width": width,
        "height": height,
        "raw_payload": decompressed,
        "pixel_data": pixel_data,
        "byte_size": len(raw),
        "bit_depth": bit_depth,
        "color_type": color_type,
    }


def _extract_figma_layout_expectation(design_context: dict[str, Any]) -> dict[str, Any]:
    frame = design_context.get("frame")
    if isinstance(frame, dict):
        width = int(frame.get("width", 0) or 0)
        height = int(frame.get("height", 0) or 0)
        return {"width": width, "height": height}
    return {"width": 0, "height": 0}


def _resolve_project_file(project_root: Path, raw: str, default_rel: str) -> Path:
    value = str(raw).strip()
    if not value:
        return (project_root / default_rel).resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (project_root / value).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def _parse_texture_rect_nodes(scene_file: Path) -> list[dict[str, Any]]:
    text = _safe_read_text(scene_file)
    if not text:
        return []
    out: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[node "):
            if current and {"name", "top", "bottom", "left", "right"} <= set(current.keys()):
                out.append(current)
            match = re.search(r'name="([^"]+)"\s+type="([^"]+)"', stripped)
            if match and match.group(2) == "TextureRect":
                current = {"name": match.group(1)}
            else:
                current = None
            continue
        if current is None:
            continue
        if stripped.startswith("offset_left ="):
            current["left"] = float(stripped.split("=", 1)[1].strip())
        elif stripped.startswith("offset_top ="):
            current["top"] = float(stripped.split("=", 1)[1].strip())
        elif stripped.startswith("offset_right ="):
            current["right"] = float(stripped.split("=", 1)[1].strip())
        elif stripped.startswith("offset_bottom ="):
            current["bottom"] = float(stripped.split("=", 1)[1].strip())
    if current and {"name", "top", "bottom", "left", "right"} <= set(current.keys()):
        out.append(current)
    return out


def _build_uniform_height_plan(
    scene_file: Path,
    target_height: float,
    node_name_pattern: str,
) -> dict[str, Any]:
    nodes = _parse_texture_rect_nodes(scene_file)
    if target_height <= 0 or not nodes:
        return {"target_height": target_height, "matched_nodes": [], "adjustments": []}
    pattern = re.compile(node_name_pattern) if node_name_pattern else re.compile(r".*")
    adjustments: list[dict[str, Any]] = []
    for node in nodes:
        name = str(node.get("name", ""))
        if not pattern.search(name):
            continue
        old_w = float(node["right"]) - float(node["left"])
        old_h = float(node["bottom"]) - float(node["top"])
        if old_h <= 0:
            continue
        scale = target_height / old_h
        new_w = round(old_w * scale, 3)
        new_h = round(target_height, 3)
        new_right = round(float(node["left"]) + new_w, 3)
        new_bottom = round(float(node["top"]) + new_h, 3)
        adjustments.append(
            {
                "node": name,
                "old_size": {"width": round(old_w, 3), "height": round(old_h, 3)},
                "new_size": {"width": new_w, "height": new_h},
                "scale_factor": round(scale, 6),
                "patch_hint": {
                    "offset_right": new_right,
                    "offset_bottom": new_bottom,
                },
            }
        )
    matched = [a["node"] for a in adjustments]
    return {
        "target_height": round(target_height, 3),
        "matched_nodes": matched,
        "adjustments": adjustments,
    }


def _resolve_compare_report_payload(compare_report_file: Path) -> tuple[dict[str, Any], Path]:
    payload = _read_json_file(compare_report_file)
    if isinstance(payload.get("visual_diff"), dict) and str(payload.get("run_id", "")).strip():
        return payload, compare_report_file
    report_ref = str(payload.get("report_file", "")).strip()
    if report_ref:
        resolved = _resolve_existing_file(report_ref, "report_file")
        full = _read_json_file(resolved)
        if isinstance(full.get("visual_diff"), dict) and str(full.get("run_id", "")).strip():
            return full, resolved
    return payload, compare_report_file


def _compute_resized_diff_ratio(figma_file: Path, game_file: Path, expected_w: int, expected_h: int) -> tuple[float, dict[str, Any]]:
    info: dict[str, Any] = {"resized_for_compare": False, "method": "raw_payload"}
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return 1.0, info
    try:
        figma_img = Image.open(figma_file).convert("RGB")
        game_img = Image.open(game_file).convert("RGB")
        if figma_img.size != (expected_w, expected_h):
            figma_img = figma_img.resize((expected_w, expected_h))
            info["resized_for_compare"] = True
        if game_img.size != (expected_w, expected_h):
            game_img = game_img.resize((expected_w, expected_h))
            info["resized_for_compare"] = True
        info["method"] = "pillow_rgb"
        return _byte_diff_ratio(figma_img.tobytes(), game_img.tobytes()), info
    except Exception as exc:  # pylint: disable=broad-except
        info["error"] = str(exc)
        return 1.0, info


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
    report_path = project_root / cfg.report_dir_rel / "plugin_install_report.json"
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
            "report_dir_rel": cfg.report_dir_rel,
            "exp_dir_rel": cfg.exp_dir_rel,
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
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name=f"context_{mode}",
        payload={
            "tool": f"{mode}_project_context",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "mode": mode,
            "files_scanned_count": len(files),
            "context_dir": built["documents"]["context_dir"],
            "index_json": built["documents"]["index_json"],
        },
    )
    legacy_hints = _legacy_layout_hints(project_root)
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
        "exp_runtime": exp_artifact,
        "legacy_layout_hints": legacy_hints,
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
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="flow_seed_last",
        payload={
            "tool": "generate_flow_seed",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "flow_id": flow_id,
            "flow_file": str(output_path),
            "seed_strategy": strategy,
            "step_count": len(seeded_steps),
        },
    )
    legacy_hints = _legacy_layout_hints(project_root)
    return {
        "status": "generated",
        "project_root": str(project_root),
        "flow_id": flow_id,
        "flow_file": str(output_path),
        "seed_strategy": strategy,
        "step_count": len(seeded_steps),
        "from_action_candidates": len(action_candidates),
        "from_assertion_candidates": len(assertion_candidates),
        "exp_runtime": exp_artifact,
        "legacy_layout_hints": legacy_hints,
    }


def _tool_run_game_basic_test_flow(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    flow_file_raw = str(arguments.get("flow_file", "")).strip()
    if flow_file_raw:
        flow_file = Path(flow_file_raw)
        if not flow_file.is_absolute():
            flow_file = (project_root / flow_file).resolve()
        else:
            flow_file = flow_file.resolve()
    else:
        flow_id = str(arguments.get("flow_id", "")).strip() or "basic_game_test_flow"
        flow_slug = _slugify(flow_id)
        flow_file = (project_root / cfg.seed_flow_dir_rel / f"{flow_slug}.json").resolve()
    if not flow_file.exists() or not flow_file.is_file():
        raise AppError("INVALID_ARGUMENT", f"flow file not found: {flow_file}")
    flow_data = _read_json_file(flow_file)
    raw_timeout = arguments.get("step_timeout_ms", 30_000)
    try:
        step_timeout_ms = int(raw_timeout) if raw_timeout is not None else 30_000
    except (TypeError, ValueError):
        step_timeout_ms = 30_000
    if step_timeout_ms <= 0:
        step_timeout_ms = 30_000
    run_id_opt = str(arguments.get("run_id", "")).strip() or None
    runtime_dir = _exp_runtime_dir(project_root, cfg)
    opts = FlowRunOptions(
        project_root=project_root,
        flow_file=flow_file,
        report_dir=runtime_dir,
        step_timeout_ms=step_timeout_ms,
        run_id=run_id_opt,
        fail_fast=bool(arguments.get("fail_fast", True)),
        shell_report=bool(arguments.get("shell_report", False)),
    )
    runner = FlowRunner(opts)
    try:
        report = runner.run(flow_data)
    except FlowExecutionTimeout as exc:
        rep = exc.report or {}
        raise AppError(
            "TIMEOUT",
            str(exc),
            {
                "run_id": exc.run_id,
                "step_index": exc.step_index,
                "step_id": exc.step_id,
                "execution_report": rep,
            },
        ) from exc
    except FlowExecutionStepFailed as exc:
        rep = exc.report or {}
        raise AppError(
            "STEP_FAILED",
            str(exc),
            {
                "run_id": exc.run_id,
                "step_index": exc.step_index,
                "step_id": exc.step_id,
                "execution_report": rep,
            },
        ) from exc
    legacy_hints = _legacy_layout_hints(project_root)
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="basic_game_test_execution_last",
        payload={
            "tool": "run_game_basic_test_flow",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "flow_file": str(flow_file),
            "flow_id": str(flow_data.get("flowId", "")),
            "run_id": report["run_id"],
            "status": report["status"],
            "execution_report": report,
        },
    )
    return {
        "status": report.get("status", "passed"),
        "project_root": str(project_root),
        "flow_file": str(flow_file),
        "execution_report": report,
        "exp_runtime": exp_artifact,
        "legacy_layout_hints": legacy_hints,
    }


def _tool_figma_design_to_baseline(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    figma_file_key = str(arguments.get("figma_file_key", "")).strip()
    figma_node_id = str(arguments.get("figma_node_id", "")).strip()
    if not figma_file_key:
        raise AppError("INVALID_ARGUMENT", "figma_file_key is required")
    if not figma_node_id:
        raise AppError("INVALID_ARGUMENT", "figma_node_id is required")
    screenshot_path = _resolve_existing_file(str(arguments.get("figma_screenshot_file", "")), "figma_screenshot_file")
    context = arguments.get("figma_design_context", {})
    if context and not isinstance(context, dict):
        raise AppError("INVALID_ARGUMENT", "figma_design_context must be an object")
    context = context if isinstance(context, dict) else {}
    baseline_slug = _slugify(f"{figma_file_key}_{figma_node_id}")
    baseline_dir = _exp_runtime_dir(project_root, cfg) / "figma"
    baseline_json_path = baseline_dir / f"figma_baseline_{baseline_slug}.json"
    screenshot_copy = baseline_dir / f"figma_screenshot_{baseline_slug}.png"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    screenshot_copy = _convert_image_to_png_if_needed(screenshot_path, screenshot_copy)
    figma_metrics = _parse_png_metrics(screenshot_copy)
    payload = {
        "generated_at": _utc_iso(),
        "figma_ref": {
            "file_key": figma_file_key,
            "node_id": figma_node_id,
            "version": str(arguments.get("figma_version", "")).strip() or "latest",
        },
        "figma_screenshot_file": str(screenshot_copy),
        "figma_design_context": context,
        "expected_layout": _extract_figma_layout_expectation(context),
        "expected_image_height": float(arguments.get("image_target_height", 120)),
        "screenshot_metrics": {
            "format": figma_metrics.get("format"),
            "width": figma_metrics.get("width"),
            "height": figma_metrics.get("height"),
            "byte_size": figma_metrics.get("byte_size"),
        },
    }
    _write_text(baseline_json_path, json.dumps(payload, ensure_ascii=False, indent=2))
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="figma_baseline_last",
        payload={
            "tool": "figma_design_to_baseline",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "baseline_file": str(baseline_json_path),
            "figma_ref": payload["figma_ref"],
        },
    )
    return {
        "status": "generated",
        "project_root": str(project_root),
        "baseline_file": str(baseline_json_path),
        "figma_screenshot_file": str(screenshot_copy),
        "figma_ref": payload["figma_ref"],
        "exp_runtime": exp_artifact,
    }


def _tool_compare_figma_game_ui(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    baseline_file = _resolve_existing_file(str(arguments.get("figma_baseline_file", "")), "figma_baseline_file")
    game_snapshot_file = _resolve_existing_file(str(arguments.get("game_snapshot_file", "")), "game_snapshot_file")
    baseline = _read_json_file(baseline_file)
    figma_screenshot_file = _resolve_existing_file(
        str(baseline.get("figma_screenshot_file", "")),
        "figma_screenshot_file",
    )
    figma_metrics = _parse_png_metrics(figma_screenshot_file)
    game_metrics = _parse_png_metrics(game_snapshot_file)
    pixel_threshold = float(arguments.get("pixel_threshold", 0.03))
    perceptual_threshold = float(arguments.get("perceptual_threshold", 0.97))
    resize_to_baseline = bool(arguments.get("resize_to_baseline", True))
    same_resolution = (
        int(figma_metrics.get("width", 0)) > 0
        and int(figma_metrics.get("width", 0)) == int(game_metrics.get("width", 0))
        and int(figma_metrics.get("height", 0)) == int(game_metrics.get("height", 0))
    )
    figma_payload = figma_metrics.get("pixel_data", b"") or figma_metrics.get("raw_payload", b"") or figma_screenshot_file.read_bytes()
    game_payload = game_metrics.get("pixel_data", b"") or game_metrics.get("raw_payload", b"") or game_snapshot_file.read_bytes()
    resize_info: dict[str, Any] = {"resized_for_compare": False, "method": "raw_payload"}
    can_compare_raw = same_resolution and len(figma_payload) == len(game_payload) and len(figma_payload) > 0
    if resize_to_baseline and int(figma_metrics.get("width", 0)) > 0 and int(figma_metrics.get("height", 0)) > 0:
        pixel_diff_ratio, resize_info = _compute_resized_diff_ratio(
            figma_screenshot_file,
            game_snapshot_file,
            int(figma_metrics.get("width", 0)),
            int(figma_metrics.get("height", 0)),
        )
    elif can_compare_raw:
        pixel_diff_ratio = _byte_diff_ratio(figma_payload, game_payload)
    else:
        pixel_diff_ratio = 1.0
    perceptual_score = round(max(0.0, 1.0 - pixel_diff_ratio), 6)
    expected_layout = baseline.get("expected_layout", {})
    layout_diff = {
        "expected_width": int(expected_layout.get("width", 0) or 0),
        "expected_height": int(expected_layout.get("height", 0) or 0),
        "actual_width": int(game_metrics.get("width", 0) or 0),
        "actual_height": int(game_metrics.get("height", 0) or 0),
    }
    layout_diff["dimension_mismatch"] = bool(
        layout_diff["expected_width"]
        and layout_diff["expected_height"]
        and (
            layout_diff["expected_width"] != layout_diff["actual_width"]
            or layout_diff["expected_height"] != layout_diff["actual_height"]
        )
    )
    visual_pass = pixel_diff_ratio <= pixel_threshold and perceptual_score >= perceptual_threshold
    overall_status = "pass" if visual_pass and not layout_diff["dimension_mismatch"] else "fail"
    run_id = _slugify(f"{baseline.get('figma_ref', {}).get('file_key', 'figma')}_{datetime.now(timezone.utc).timestamp()}")
    report_payload = {
        "tool": "compare_figma_game_ui",
        "generated_at": _utc_iso(),
        "run_id": run_id,
        "project_root": str(project_root),
        "figma_ref": baseline.get("figma_ref", {}),
        "figma_baseline_file": str(baseline_file),
        "game_snapshot_file": str(game_snapshot_file),
        "overall_status": overall_status,
        "visual_diff": {
            "pixel_diff_ratio": pixel_diff_ratio,
            "perceptual_score": perceptual_score,
            "pixel_threshold": pixel_threshold,
            "perceptual_threshold": perceptual_threshold,
            "same_resolution": same_resolution,
            "raw_payload_compatible": can_compare_raw,
            "resize_to_baseline": resize_to_baseline,
            "resize_info": resize_info,
        },
        "layout_diff": layout_diff,
        "hot_regions": [],
        "next_action": "request_approval" if overall_status != "pass" else "accept",
        "hashes": {
            "figma_sha256": hashlib.sha256(figma_screenshot_file.read_bytes()).hexdigest(),
            "game_sha256": hashlib.sha256(game_snapshot_file.read_bytes()).hexdigest(),
        },
    }
    report_name = _slugify(str(arguments.get("report_basename", "")).strip() or f"compare_figma_game_ui_{run_id}")
    report_file = _exp_runtime_dir(project_root, cfg) / f"{report_name}.json"
    _write_text(report_file, json.dumps(report_payload, ensure_ascii=False, indent=2))
    exp_artifact = _write_exp_runtime_artifact(
        project_root=project_root,
        cfg=cfg,
        artifact_name="compare_figma_game_ui_last",
        payload={
            "tool": "compare_figma_game_ui",
            "generated_at": _utc_iso(),
            "project_root": str(project_root),
            "report_file": str(report_file),
            "overall_status": overall_status,
            "run_id": run_id,
        },
    )
    return {
        "status": "compared",
        "project_root": str(project_root),
        "report_file": str(report_file),
        "run_id": run_id,
        "overall_status": overall_status,
        "visual_diff": report_payload["visual_diff"],
        "layout_diff": layout_diff,
        "next_action": report_payload["next_action"],
        "exp_runtime": exp_artifact,
    }


def _tool_annotate_ui_mismatch(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    compare_report_file = _resolve_existing_file(str(arguments.get("compare_report_file", "")), "compare_report_file")
    compare_payload, resolved_compare_report = _resolve_compare_report_payload(compare_report_file)
    mismatches: list[dict[str, Any]] = []
    layout = compare_payload.get("layout_diff", {})
    if isinstance(layout, dict) and layout.get("dimension_mismatch"):
        mismatches.append(
            {
                "severity": "high",
                "type": "dimension_mismatch",
                "figma_ref": compare_payload.get("figma_ref", {}),
                "evidence": {
                    "expected": [layout.get("expected_width"), layout.get("expected_height")],
                    "actual": [layout.get("actual_width"), layout.get("actual_height")],
                },
            }
        )
    visual = compare_payload.get("visual_diff", {})
    if isinstance(visual, dict) and float(visual.get("pixel_diff_ratio", 0.0)) > float(visual.get("pixel_threshold", 0.03)):
        mismatches.append(
            {
                "severity": "medium",
                "type": "visual_diff",
                "figma_ref": compare_payload.get("figma_ref", {}),
                "evidence": {
                    "pixel_diff_ratio": visual.get("pixel_diff_ratio"),
                    "threshold": visual.get("pixel_threshold"),
                    "perceptual_score": visual.get("perceptual_score"),
                },
            }
        )
    annotation_payload = {
        "tool": "annotate_ui_mismatch",
        "generated_at": _utc_iso(),
        "run_id": compare_payload.get("run_id"),
        "project_root": str(project_root),
        "compare_report_file": str(resolved_compare_report),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "summary": "no mismatch" if not mismatches else "mismatch detected",
    }
    report_file = _exp_runtime_dir(project_root, cfg) / f"ui_mismatch_annotations_{_slugify(str(compare_payload.get('run_id', 'last')))}.json"
    _write_text(report_file, json.dumps(annotation_payload, ensure_ascii=False, indent=2))
    return {
        "status": "annotated",
        "project_root": str(project_root),
        "annotation_file": str(report_file),
        "mismatch_count": len(mismatches),
    }


def _tool_approve_ui_fix_plan(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    compare_report_file = _resolve_existing_file(str(arguments.get("compare_report_file", "")), "compare_report_file")
    approved = bool(arguments.get("approved", False))
    token = str(arguments.get("approval_token", "")).strip()
    if approved and not token:
        raise AppError("INVALID_ARGUMENT", "approval_token is required when approved=true")
    compare_payload, resolved_compare_report = _resolve_compare_report_payload(compare_report_file)
    run_id = _slugify(str(compare_payload.get("run_id", "last")))
    approval_payload = {
        "tool": "approve_ui_fix_plan",
        "generated_at": _utc_iso(),
        "project_root": str(project_root),
        "run_id": compare_payload.get("run_id"),
        "compare_report_file": str(resolved_compare_report),
        "approved": approved,
        "approval_token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest() if token else "",
    }
    approval_file = _exp_runtime_dir(project_root, cfg) / f"ui_fix_approval_{run_id}.json"
    _write_text(approval_file, json.dumps(approval_payload, ensure_ascii=False, indent=2))
    return {
        "status": "recorded",
        "project_root": str(project_root),
        "approval_file": str(approval_file),
        "approved": approved,
        "run_id": compare_payload.get("run_id"),
    }


def _tool_suggest_ui_fix_patch(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    cfg = _resolve_runtime_config(ctx, arguments, project_root=project_root)
    compare_report_file = _resolve_existing_file(str(arguments.get("compare_report_file", "")), "compare_report_file")
    approval_file = _resolve_existing_file(str(arguments.get("approval_file", "")), "approval_file")
    compare_payload, resolved_compare_report = _resolve_compare_report_payload(compare_report_file)
    approval_payload = _read_json_file(approval_file)
    if not bool(approval_payload.get("approved", False)):
        raise AppError("INVALID_ARGUMENT", "fix suggestion requires approved=true in approval_file")
    baseline_file = _resolve_existing_file(str(compare_payload.get("figma_baseline_file", "")), "figma_baseline_file")
    baseline_payload = _read_json_file(baseline_file)
    target_height = float(
        arguments.get(
            "image_target_height",
            baseline_payload.get("expected_image_height", 120),
        )
    )
    node_pattern = str(arguments.get("image_node_pattern", "Image|Preview")).strip() or "Image|Preview"
    scene_file = _resolve_project_file(project_root, str(arguments.get("scene_file", "")), "scenes/main_scene_example.tscn")
    uniform_plan: dict[str, Any] = {"target_height": target_height, "matched_nodes": [], "adjustments": []}
    if scene_file.exists():
        uniform_plan = _build_uniform_height_plan(scene_file, target_height, node_pattern)
    suggestions: list[dict[str, Any]] = []
    layout = compare_payload.get("layout_diff", {})
    if isinstance(layout, dict) and layout.get("dimension_mismatch"):
        suggestions.append(
            {
                "file": "scenes/main_scene_example.tscn",
                "reason": "scene root dimension differs from figma baseline",
                "figma_expected": {"width": layout.get("expected_width"), "height": layout.get("expected_height")},
                "game_actual": {"width": layout.get("actual_width"), "height": layout.get("actual_height")},
                "proposed_change": "adjust root control anchors/size to match figma frame dimensions",
                "confidence": 0.72,
                "risk": "medium",
            }
        )
    visual = compare_payload.get("visual_diff", {})
    if isinstance(visual, dict) and float(visual.get("pixel_diff_ratio", 0.0)) > float(visual.get("pixel_threshold", 0.03)):
        suggestions.append(
            {
                "file": str(scene_file),
                "reason": "visual diff exceeds threshold",
                "figma_expected": {"pixel_diff_ratio_max": visual.get("pixel_threshold")},
                "game_actual": {"pixel_diff_ratio": visual.get("pixel_diff_ratio")},
                "proposed_change": "align spacing/font/color tokens with figma design context",
                "confidence": 0.64,
                "risk": "low",
            }
        )
        if uniform_plan.get("adjustments"):
            suggestions.append(
                {
                    "file": str(scene_file),
                    "reason": "image size drift can be reduced by uniform scaling to target height",
                    "figma_expected": {"image_height": target_height},
                    "game_actual": {
                        "matched_nodes": uniform_plan.get("matched_nodes", []),
                        "first_old_height": (
                            uniform_plan.get("adjustments", [{}])[0].get("old_size", {}).get("height")
                            if uniform_plan.get("adjustments")
                            else None
                        ),
                    },
                    "proposed_change": "apply uniform scaling to matched image nodes so rendered height equals target",
                    "uniform_scale_plan": uniform_plan,
                    "confidence": 0.86,
                    "risk": "low",
                }
            )
    max_suggestions = int(arguments.get("max_suggestions", 10))
    if max_suggestions <= 0:
        max_suggestions = 1
    suggestions = suggestions[:max_suggestions]
    run_id = _slugify(str(compare_payload.get("run_id", "last")))
    payload = {
        "tool": "suggest_ui_fix_patch",
        "generated_at": _utc_iso(),
        "project_root": str(project_root),
        "run_id": compare_payload.get("run_id"),
        "compare_report_file": str(resolved_compare_report),
        "approval_file": str(approval_file),
        "uniform_scale_plan": uniform_plan,
        "suggestions": suggestions,
        "suggestion_count": len(suggestions),
    }
    suggestion_file = _exp_runtime_dir(project_root, cfg) / f"ui_fix_suggestions_{run_id}.json"
    _write_text(suggestion_file, json.dumps(payload, ensure_ascii=False, indent=2))
    return {
        "status": "suggested",
        "project_root": str(project_root),
        "suggestion_file": str(suggestion_file),
        "run_id": compare_payload.get("run_id"),
        "suggestion_count": len(suggestions),
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
    project_root_raw = str(arguments.get("project_root", "")).strip()
    project_root = Path(project_root_raw).resolve() if project_root_raw else None
    exp_runtime_info: dict[str, Any] = {"exp_runtime_dir_rel": f"{cfg.exp_dir_rel}/runtime"}
    legacy_hints: list[dict[str, str]] = []
    if project_root is not None and project_root.exists():
        exp_runtime_info = {
            "exp_output_dir": str((project_root / cfg.exp_dir_rel).resolve()),
            "exp_runtime_dir": str(_exp_runtime_dir(project_root, cfg)),
            "exp_runtime_dir_rel": f"{cfg.exp_dir_rel}/runtime",
        }
        legacy_hints = _legacy_layout_hints(project_root)
    return {
        "server_name": cfg.server_name,
        "server_version": cfg.server_version,
        "repo_root": str(ctx.repo_root),
        "plugin_template_dir": str(cfg.plugin_template_dir),
        "workspace_output_dir": DEFAULT_WORKSPACE_DIR_REL,
        "context_output_dir": cfg.context_dir_rel,
        "seed_flow_output_dir": cfg.seed_flow_dir_rel,
        "report_output_dir": cfg.report_dir_rel,
        "exp_output_dir": cfg.exp_dir_rel,
        "exp_runtime": exp_runtime_info,
        "config_sources": cfg.config_sources,
        "legacy_layout_hints": legacy_hints,
        "tool_capabilities": {
            "run_game_basic_test_flow": {
                "implemented": True,
                "status": "implemented",
                "phase": "task2_runtime",
            }
        },
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
            "figma_design_to_baseline",
            "compare_figma_game_ui",
            "annotate_ui_mismatch",
            "approve_ui_fix_plan",
            "suggest_ui_fix_patch",
            "run_game_basic_test_flow",
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
        "figma_design_to_baseline": _tool_figma_design_to_baseline,
        "compare_figma_game_ui": _tool_compare_figma_game_ui,
        "annotate_ui_mismatch": _tool_annotate_ui_mismatch,
        "approve_ui_fix_plan": _tool_approve_ui_fix_plan,
        "suggest_ui_fix_patch": _tool_suggest_ui_fix_patch,
        "run_game_basic_test_flow": _tool_run_game_basic_test_flow,
    }


def _build_tool_specs() -> dict[str, dict[str, Any]]:
    base_props: dict[str, Any] = {
        "project_root": {"type": "string", "description": "Absolute path to target Godot project root."},
        "config_file": {"type": "string", "description": "Optional runtime config JSON file path."},
    }
    return {
        "get_mcp_runtime_info": {
            "description": "Get runtime and tool metadata for PointerGPF MCP.",
            "inputSchema": {
                "type": "object",
                "properties": {"config_file": base_props["config_file"], "project_root": base_props["project_root"]},
            },
        },
        "get_adapter_contract": {
            "description": "Return adapter contract JSON for Godot integration.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        "install_godot_plugin": {
            "description": "Install PointerGPF plugin files and enable plugin in project.godot.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": dict(base_props),
            },
        },
        "enable_godot_plugin": {
            "description": "Enable existing PointerGPF plugin in project.godot.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": dict(base_props),
            },
        },
        "update_godot_plugin": {
            "description": "Overwrite plugin files and ensure plugin enabled.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": dict(base_props),
            },
        },
        "check_plugin_status": {
            "description": "Check plugin files and plugin enabled status.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": dict(base_props),
            },
        },
        "init_project_context": {
            "description": "Initialize project context and candidate documents.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "max_files": {"type": "integer", "description": "Maximum files to scan."},
                },
            },
        },
        "refresh_project_context": {
            "description": "Refresh project context incrementally.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "max_files": {"type": "integer", "description": "Maximum files to scan."},
                },
            },
        },
        "generate_flow_seed": {
            "description": "Generate flow seed JSON from context index.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "flow_id": {"type": "string"},
                    "flow_name": {"type": "string"},
                    "output_file": {"type": "string"},
                    "strategy": {"type": "string", "enum": ["auto", "ui", "exploration", "builder", "generic"]},
                },
            },
        },
        "run_game_basic_test_flow": {
            "description": "Run a basic gameplay flow test via file bridge (command.json/response.json) with three-phase event reporting.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root"],
                "properties": {
                    **base_props,
                    "flow_id": {"type": "string", "description": "Logical flow identifier when not using flow_file."},
                    "flow_file": {"type": "string", "description": "Path to flow JSON file."},
                    "step_timeout_ms": {"type": "integer", "description": "Per-step timeout in milliseconds."},
                    "fail_fast": {"type": "boolean", "description": "Stop on first step failure."},
                    "shell_report": {"type": "boolean", "description": "Emit shell-oriented report artifacts when supported."},
                },
            },
        },
        "figma_design_to_baseline": {
            "description": "Persist Figma design context and screenshot as baseline artifact.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "figma_file_key", "figma_node_id", "figma_screenshot_file"],
                "properties": {
                    **base_props,
                    "figma_file_key": {"type": "string"},
                    "figma_node_id": {"type": "string"},
                    "figma_version": {"type": "string"},
                    "figma_screenshot_file": {"type": "string"},
                    "figma_design_context": {"type": "object"},
                    "image_target_height": {"type": "number"},
                },
            },
        },
        "compare_figma_game_ui": {
            "description": "Compare Figma baseline screenshot/context against game UI screenshot.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "figma_baseline_file", "game_snapshot_file"],
                "properties": {
                    **base_props,
                    "figma_baseline_file": {"type": "string"},
                    "game_snapshot_file": {"type": "string"},
                    "pixel_threshold": {"type": "number"},
                    "perceptual_threshold": {"type": "number"},
                    "resize_to_baseline": {"type": "boolean"},
                    "report_basename": {"type": "string"},
                },
            },
        },
        "annotate_ui_mismatch": {
            "description": "Generate mismatch annotation report from compare result.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "compare_report_file"],
                "properties": {
                    **base_props,
                    "compare_report_file": {"type": "string"},
                },
            },
        },
        "approve_ui_fix_plan": {
            "description": "Record approval gate result for UI fix suggestions.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "compare_report_file", "approved"],
                "properties": {
                    **base_props,
                    "compare_report_file": {"type": "string"},
                    "approved": {"type": "boolean"},
                    "approval_token": {"type": "string"},
                },
            },
        },
        "suggest_ui_fix_patch": {
            "description": "Generate UI fix suggestion patch draft from compare report.",
            "inputSchema": {
                "type": "object",
                "required": ["project_root", "compare_report_file", "approval_file"],
                "properties": {
                    **base_props,
                    "compare_report_file": {"type": "string"},
                    "approval_file": {"type": "string"},
                    "max_suggestions": {"type": "integer"},
                    "scene_file": {"type": "string"},
                    "image_target_height": {"type": "number"},
                    "image_node_pattern": {"type": "string"},
                },
            },
        },
    }


def _read_mcp_message() -> dict[str, Any] | None:
    global _MCP_IO_MODE
    # Be lenient on transport framing:
    # 1) Standard MCP stdio headers (Content-Length)
    # 2) JSON lines (some clients/proxies write one JSON object per line)
    while True:
        first = sys.stdin.buffer.readline()
        if not first:
            return None
        if first in (b"\r\n", b"\n"):
            continue

        first_text = first.decode("utf-8", errors="replace").strip()
        if first_text.startswith("{"):
            try:
                payload = json.loads(first_text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                _MCP_IO_MODE = "jsonl"
                return payload
            continue

        headers: dict[str, str] = {}
        if ":" in first_text:
            key, value = first_text.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text or ":" not in text:
                continue
            key, value = text.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        content_length_raw = headers.get("content-length", "")
        if not content_length_raw:
            continue
        try:
            content_length = int(content_length_raw)
        except ValueError:
            continue
        body = sys.stdin.buffer.read(content_length)
        if not body:
            continue
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            _MCP_IO_MODE = "header"
            return payload


def _write_mcp_message(payload: dict[str, Any]) -> None:
    body_text = json.dumps(payload, ensure_ascii=False)
    if _MCP_IO_MODE == "jsonl":
        sys.stdout.buffer.write((body_text + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
        return
    body = body_text.encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _mcp_jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _mcp_jsonrpc_error(request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _run_stdio_mcp(ctx: ServerCtx, tool_map: dict[str, Any], startup_config_file: str | None = None) -> int:
    tool_specs = _build_tool_specs()
    while True:
        req = _read_mcp_message()
        if req is None:
            return 0
        request_id = req.get("id")
        method = str(req.get("method", "")).strip()
        params = req.get("params", {})
        if not isinstance(params, dict):
            params = {}
        is_notification = "id" not in req
        try:
            if method == "initialize":
                if is_notification:
                    continue
                _write_mcp_message(
                    _mcp_jsonrpc_result(
                        request_id,
                        {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": DEFAULT_SERVER_NAME, "version": DEFAULT_SERVER_VERSION},
                        },
                    )
                )
                continue
            if method == "notifications/initialized":
                continue
            if method == "ping":
                if not is_notification:
                    _write_mcp_message(_mcp_jsonrpc_result(request_id, {}))
                continue
            if method == "tools/list":
                if is_notification:
                    continue
                tools = [
                    {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
                    for name, spec in tool_specs.items()
                ]
                _write_mcp_message(_mcp_jsonrpc_result(request_id, {"tools": tools}))
                continue
            if method == "tools/call":
                if is_notification:
                    continue
                tool_name = str(params.get("name", "")).strip()
                args_payload = params.get("arguments", {})
                if not isinstance(args_payload, dict):
                    raise AppError("INVALID_ARGUMENT", "tool arguments must be an object")
                if startup_config_file and "config_file" not in args_payload:
                    args_payload["config_file"] = startup_config_file
                handler = tool_map.get(tool_name)
                if handler is None:
                    raise AppError("UNSUPPORTED_TOOL", f"unsupported tool: {tool_name}")
                result = handler(ctx, args_payload)
                _write_mcp_message(
                    _mcp_jsonrpc_result(
                        request_id,
                        {
                            "structuredContent": result,
                            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                        },
                    )
                )
                continue
            if is_notification:
                continue
            _write_mcp_message(_mcp_jsonrpc_error(request_id, -32601, f"Method not found: {method}"))
        except AppError as exc:
            if not is_notification:
                _write_mcp_message(_mcp_jsonrpc_error(request_id, -32000, exc.message, exc.as_dict()))
        except Exception as exc:  # pylint: disable=broad-except
            if not is_notification:
                _write_mcp_message(_mcp_jsonrpc_error(request_id, -32603, "Internal error", {"error": str(exc)}))


def _run_cli_mode(args: argparse.Namespace, ctx: ServerCtx, tool_map: dict[str, Any]) -> int:
    if not args.tool:
        raise AppError("INVALID_ARGUMENT", "--tool is required in CLI mode")
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PointerGPF MCP server")
    parser.add_argument("--tool", required=False, help="Tool name for CLI compatibility mode")
    parser.add_argument("--stdio", action="store_true", help="Force stdio MCP server mode")
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
        if args.stdio or not args.tool:
            return _run_stdio_mcp(ctx, tool_map, startup_config_file=args.config_file)
        return _run_cli_mode(args, ctx, tool_map)
    except AppError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        print(json.dumps({"ok": False, "error": {"code": "INTERNAL_ERROR", "message": str(exc)}}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
