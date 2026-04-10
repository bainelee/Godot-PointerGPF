"""Optional L2 repair hook after bug_fix_strategies (L1) apply_patch."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

L2TryPatchFn = Callable[[Path, str, dict[str, Any], dict[str, Any]], dict[str, Any]]


def build_l2_try_patch_from_env() -> L2TryPatchFn | None:
    """If ``GPF_REPAIR_BACKEND_CMD`` is set, return a callable that runs it and parses last stdout line as JSON.

    The command is expanded with ``{payload_file}`` and ``{project_root}`` placeholders. The subprocess should
    print one JSON object on the last non-empty line of stdout, e.g. ``{"applied": true, "changed_files": [], "notes": ""}``.
    """
    cmd = str(os.environ.get("GPF_REPAIR_BACKEND_CMD", "")).strip()
    if not cmd:
        return None

    def try_patch(
        project_root: Path,
        issue: str,
        diagnosis: dict[str, Any],
        verification: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "project_root": str(project_root),
            "issue": issue,
            "diagnosis": diagnosis,
            "verification": verification,
        }
        fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="gpf-l2-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            full_cmd = cmd.format(payload_file=tmp_path, project_root=str(project_root))
            proc = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            if proc.returncode != 0:
                return {
                    "applied": False,
                    "changed_files": [],
                    "notes": (f"L2 subprocess exit {proc.returncode}: " + (proc.stderr or "")[:500]).strip(),
                    "backend_id": "subprocess_json",
                }
            lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
            line = lines[-1] if lines else ""
            data = json.loads(line) if line else {}
            if not isinstance(data, dict):
                return {"applied": False, "changed_files": [], "notes": "L2 stdout last line not a JSON object"}
            return {
                "applied": bool(data.get("applied")),
                "changed_files": [str(x) for x in (data.get("changed_files") or []) if x is not None],
                "notes": str(data.get("notes", "")),
                "backend_id": "subprocess_json",
            }
        except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired, ValueError) as exc:
            return {"applied": False, "changed_files": [], "notes": str(exc), "backend_id": "subprocess_json"}
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass

    return try_patch
