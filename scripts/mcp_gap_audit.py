#!/usr/bin/env python3
"""Compare legacy old-archives-sp MCP surface and paths against the current repo."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _git_ls_tree(repo: str, commit: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "-C", repo, "ls-tree", "-r", "--name-only", commit],
        text=True,
        encoding="utf-8",
    )
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def _extract_old_tool_surface(repo: str, commit: str) -> list[str]:
    src = subprocess.check_output(
        ["git", "-C", repo, "show", f"{commit}:tools/game-test-runner/mcp/server.py"],
        text=True,
        encoding="utf-8",
    )
    block_m = re.search(
        r"TOOL_TO_METHOD:\s*dict\[str,\s*str\]\s*=\s*\{([\s\S]*?)\n\s+\}\s*\n\s+SNAPSHOT_REQUIRED_TOOLS:",
        src,
    )
    if not block_m:
        raise RuntimeError(
            "failed to locate TOOL_TO_METHOD dict in old tools/game-test-runner/mcp/server.py"
        )
    block = block_m.group(1)
    tools = sorted(set(re.findall(r'"([a-z0-9_]+)"\s*:\s*"[a-zA-Z0-9_]+"', block)))
    return tools


def _extract_new_tool_surface(repo: str) -> list[str]:
    path = Path(repo) / "mcp" / "server.py"
    src = path.read_text(encoding="utf-8")
    tool_map_block = re.findall(
        r"def _build_tool_map\(\) -> dict\[str, Any\]:([\s\S]*?)def _build_tool_specs",
        src,
    )
    if not tool_map_block:
        return []
    tools = sorted(set(re.findall(r'"([a-z0-9_]+)"\s*:\s*_tool_', tool_map_block[0])))
    return tools


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-repo", required=True)
    parser.add_argument("--old-commit", required=True)
    parser.add_argument("--new-repo", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    try:
        old_paths = _git_ls_tree(args.old_repo, args.old_commit)
        new_paths = _git_ls_tree(args.new_repo, "HEAD")
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or str(exc), file=sys.stderr)
        return exc.returncode

    old_tools = _extract_old_tool_surface(args.old_repo, args.old_commit)
    new_tools = _extract_new_tool_surface(args.new_repo)

    prefix_list = [
        "tools/game-test-runner/core/",
        "tools/game-test-runner/mcp/",
        "tools/game-test-runner/scripts/",
        "tools/game-test-runner/config/",
        "flows/",
        "addons/test_orchestrator/",
        "docs/design/99-tools/",
        "docs/testing/",
    ]
    new_set = set(new_paths)
    missing_by_prefix: dict[str, list[str]] = {}
    for prefix in prefix_list:
        miss = sorted(p for p in old_paths if p.startswith(prefix) and p not in new_set)
        if miss:
            missing_by_prefix[prefix] = miss

    new_tool_set = set(new_tools)
    result: dict[str, Any] = {
        "old_tool_surface": old_tools,
        "new_tool_surface": new_tools,
        "missing_tools": sorted(t for t in old_tools if t not in new_tool_set),
        "missing_paths_by_prefix": {k: len(v) for k, v in missing_by_prefix.items()},
        "missing_path_samples": {k: v[:10] for k, v in missing_by_prefix.items()},
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
