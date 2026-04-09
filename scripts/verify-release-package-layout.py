#!/usr/bin/env python3
"""Verify release zip keeps all PointerGPF assets under pointer_gpf/."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify-release-package-layout.py <zip_path>", file=sys.stderr)
        return 2

    zip_path = Path(sys.argv[1]).resolve()
    if not zip_path.exists():
        print(f"zip not found: {zip_path}", file=sys.stderr)
        return 2

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())

    required_entries = {
        "pointer_gpf/mcp/server.py",
        "pointer_gpf/install/update-mcp.ps1",
        "pointer_gpf/tools/game-test-runner/mcp/server.py",
        "pointer_gpf/flows/internal/contract_force_fail_invalid_scene.json",
        "pointer_gpf/godot_plugin_template/addons/pointer_gpf/plugin.gd",
    }
    missing = sorted(item for item in required_entries if item not in names)
    if missing:
        print(json.dumps({"ok": False, "missing": missing}, ensure_ascii=False))
        return 1

    payload_root_violations = sorted(
        item
        for item in names
        if item
        and not item.endswith("/")
        and item not in {"pointer-gpf.cmd", "README.md"}
        and not item.startswith("pointer_gpf/")
    )
    if payload_root_violations:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "found files outside pointer_gpf payload root",
                    "samples": payload_root_violations[:20],
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {"ok": True, "checked_required_entries": sorted(required_entries)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

