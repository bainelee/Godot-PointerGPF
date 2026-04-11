from __future__ import annotations

import re
from pathlib import Path

from .contracts import PreflightIssue, PreflightResult
from .godot_locator import load_godot_executable

_EXT_RESOURCE_SCRIPT_RE = re.compile(
    r'^\[ext_resource\s+type="Script"\s+uid="(?P<uid>uid://[^"]+)"\s+path="res://(?P<path>[^"]+)"',
    re.MULTILINE,
)


def _check_project_root(project_root: Path, issues: list[PreflightIssue], checks: dict[str, object]) -> None:
    project_file = project_root / "project.godot"
    checks["project_file"] = str(project_file)
    if not project_file.is_file():
        issues.append(
            PreflightIssue(
                code="PROJECT_FILE_MISSING",
                message="project.godot not found",
                details={"path": str(project_file)},
            )
        )


def _check_godot_executable(project_root: Path, issues: list[PreflightIssue], checks: dict[str, object]) -> None:
    try:
        executable = load_godot_executable(project_root)
    except Exception as exc:
        issues.append(
            PreflightIssue(
                code="GODOT_EXECUTABLE_NOT_CONFIGURED",
                message=str(exc),
            )
        )
        return
    checks["godot_executable"] = executable
    if not Path(executable).is_file():
        issues.append(
            PreflightIssue(
                code="GODOT_EXECUTABLE_NOT_FOUND",
                message="configured godot executable does not exist",
                details={"path": executable},
            )
        )


def _check_plugin_install(project_root: Path, issues: list[PreflightIssue], checks: dict[str, object]) -> None:
    plugin_dir = project_root / "addons" / "pointer_gpf"
    checks["plugin_dir"] = str(plugin_dir)
    expected = [
        plugin_dir / "plugin.cfg",
        plugin_dir / "plugin.gd",
        plugin_dir / "runtime_bridge.gd",
        plugin_dir / "runtime_diagnostics_writer.gd",
    ]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        issues.append(
            PreflightIssue(
                code="PLUGIN_FILES_MISSING",
                message="pointer_gpf plugin is not fully installed",
                details={"missing": missing},
            )
        )


def _check_runtime_tmp(project_root: Path, issues: list[PreflightIssue], checks: dict[str, object]) -> None:
    tmp_dir = project_root / "pointer_gpf" / "tmp"
    checks["runtime_tmp_dir"] = str(tmp_dir)
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        probe = tmp_dir / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        issues.append(
            PreflightIssue(
                code="RUNTIME_TMP_NOT_WRITABLE",
                message=str(exc),
                details={"path": str(tmp_dir)},
            )
        )


def _check_script_uid_mismatches(project_root: Path, issues: list[PreflightIssue], checks: dict[str, object]) -> None:
    mismatches: list[dict[str, str]] = []
    for scene_path in project_root.rglob("*.tscn"):
        try:
            text = scene_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _EXT_RESOURCE_SCRIPT_RE.finditer(text):
            rel_script = match.group("path").replace("/", "\\")
            script_path = project_root / rel_script
            uid_path = Path(str(script_path) + ".uid")
            if not uid_path.is_file():
                continue
            try:
                disk_uid = uid_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            scene_uid = match.group("uid").strip()
            if disk_uid and scene_uid != disk_uid:
                mismatches.append(
                    {
                        "scene_file": str(scene_path),
                        "script_path": str(script_path),
                        "scene_uid": scene_uid,
                        "disk_uid": disk_uid,
                    }
                )
    checks["script_uid_mismatch_count"] = len(mismatches)
    if mismatches:
        issues.append(
            PreflightIssue(
                code="PROJECT_RESOURCE_UID_MISMATCH",
                message="scene ext_resource script UID does not match disk .uid file",
                details={"mismatches": mismatches[:20]},
            )
        )


def run_preflight(project_root: Path) -> PreflightResult:
    root = project_root.resolve()
    issues: list[PreflightIssue] = []
    checks: dict[str, object] = {}
    _check_project_root(root, issues, checks)
    _check_godot_executable(root, issues, checks)
    _check_plugin_install(root, issues, checks)
    _check_runtime_tmp(root, issues, checks)
    _check_script_uid_mismatches(root, issues, checks)
    return PreflightResult(ok=not issues, project_root=root, issues=issues, checks=checks)

