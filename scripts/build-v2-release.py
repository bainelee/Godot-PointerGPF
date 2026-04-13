from __future__ import annotations

import argparse
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
REQUIRED_PATHS = [
    ROOT / "README.md",
    ROOT / "README.en.md",
    ROOT / "README.zh-CN.md",
    ROOT / "LICENSE",
    ROOT / "pointer_gpf_logo.png",
    ROOT / "docs",
    ROOT / "scripts",
    ROOT / "v2",
]
EXCLUDED_DIR_NAMES = {".git", ".github", ".worktrees", "tmp", "dist", "__pycache__"}
EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a minimal Pointer GPF V2 release bundle")
    parser.add_argument("--version", required=True, help="release bundle version label")
    return parser.parse_args()


def _iter_release_files() -> list[Path]:
    files: list[Path] = []
    for required in REQUIRED_PATHS:
        if not required.exists():
            raise FileNotFoundError(f"required release path is missing: {required}")
        if required.is_file():
            files.append(required)
            continue
        for path in required.rglob("*"):
            if path.is_dir():
                continue
            relative = path.relative_to(ROOT)
            if any(part in EXCLUDED_DIR_NAMES for part in relative.parts):
                continue
            if path.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
                continue
            files.append(path)
    return sorted(set(files))


def build_release_bundle(version: str) -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    bundle_path = DIST_DIR / f"pointer-gpf-v2-{version}.zip"
    files = _iter_release_files()
    with ZipFile(bundle_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.relative_to(ROOT))
    return bundle_path


def main() -> int:
    args = _parse_args()
    bundle = build_release_bundle(str(args.version).strip())
    print(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
