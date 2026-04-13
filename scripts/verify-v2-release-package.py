from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile


EXPECTED_FILES = [
    "README.md",
    "README.en.md",
    "README.zh-CN.md",
    "pointer_gpf_logo.png",
    "scripts/build-v2-release.py",
    "scripts/verify-v2-release-package.py",
    "v2/mcp_core/server.py",
    "v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a built Pointer GPF V2 release bundle")
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--project-root", required=True)
    return parser.parse_args()


def _run(command: list[str], cwd: Path) -> dict[str, object]:
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def main() -> int:
    args = _parse_args()
    bundle = Path(args.bundle).resolve()
    project_root = Path(args.project_root).resolve()
    if not bundle.is_file():
        raise FileNotFoundError(f"bundle does not exist: {bundle}")
    if not project_root.exists():
        raise FileNotFoundError(f"project root does not exist: {project_root}")
    with tempfile.TemporaryDirectory() as tmp:
        extract_root = Path(tmp) / "release"
        extract_root.mkdir(parents=True, exist_ok=True)
        with ZipFile(bundle, "r") as archive:
            archive.extractall(extract_root)
        missing_files = [path for path in EXPECTED_FILES if not (extract_root / path).exists()]
        unit_test = _run(
            ["python", "-m", "unittest", "discover", "-s", "v2/tests", "-p", "test_*.py"],
            cwd=extract_root,
        )
        command_guide = _run(
            [
                "python",
                "-m",
                "v2.mcp_core.server",
                "--tool",
                "get_user_request_command_guide",
                "--project-root",
                str(project_root),
            ],
            cwd=extract_root,
        )
        payload = {
            "bundle": str(bundle),
            "project_root": str(project_root),
            "missing_files": missing_files,
            "unit_test": unit_test,
            "command_guide": command_guide,
        }
        ok = not missing_files and unit_test["returncode"] == 0 and command_guide["returncode"] == 0
        print(json.dumps({"ok": ok, "result": payload}, ensure_ascii=False))
        return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
