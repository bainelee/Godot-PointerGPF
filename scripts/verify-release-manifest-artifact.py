#!/usr/bin/env python3
"""Download stable release zip from version_manifest.json and verify layout + MCP tool surface."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "mcp" / "version_manifest.json"

REQUIRED_ZIP_ENTRIES = (
    "pointer_gpf/mcp/server.py",
    "pointer_gpf/tools/game-test-runner/mcp/server.py",
    "pointer_gpf/flows/internal/contract_force_fail_invalid_scene.json",
)

ROOT_ALLOWED_FILES = frozenset({"pointer-gpf.cmd", "README.md"})

REQUIRED_TOOLS = frozenset(
    {
        "run_game_flow",
        "start_stepwise_flow",
        "pull_cursor_chat_plugin",
        "run_game_basic_test_flow",
        "check_test_runner_environment",
    }
)


def _normalize_zip_entry(name: str) -> str:
    return name.replace("\\", "/").strip()


def _collect_zip_names(zf: zipfile.ZipFile) -> set[str]:
    return {_normalize_zip_entry(n) for n in zf.namelist() if _normalize_zip_entry(n)}


def _layout_violations(names: set[str]) -> list[str]:
    bad: list[str] = []
    for raw in sorted(names):
        if not raw or raw.endswith("/"):
            continue
        if ".." in raw.split("/"):
            bad.append(raw)
            continue
        top = raw.split("/", 1)[0]
        if top in ROOT_ALLOWED_FILES:
            continue
        if top == "pointer_gpf" or raw.startswith("pointer_gpf/"):
            continue
        bad.append(raw)
    return bad


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for info in zf.infolist():
        name = _normalize_zip_entry(info.filename)
        if not name or ".." in name.split("/"):
            raise ValueError(f"unsafe zip entry: {info.filename!r}")
        target = (dest / name).resolve()
        try:
            target.relative_to(dest)
        except ValueError as exc:
            raise ValueError(f"zip slip: {info.filename!r}") from exc
        if name.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as out:
                out.write(src.read())


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_url(manifest: dict[str, Any]) -> str:
    try:
        url = manifest["channels"]["stable"]["artifact"]["url"]
    except (KeyError, TypeError) as exc:
        raise ValueError("manifest missing channels.stable.artifact.url") from exc
    if not isinstance(url, str) or not url.strip():
        raise ValueError("stable.artifact.url must be a non-empty string")
    return url.strip()


def _expected_sha256(manifest: dict[str, Any]) -> str | None:
    try:
        h = manifest["channels"]["stable"]["artifact"]["sha256"]
    except (KeyError, TypeError):
        return None
    if isinstance(h, str) and len(h) == 64:
        return h.lower()
    return None


def _download(url: str, dest: Path, timeout_s: int = 120) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "pointer-gpf-verify-release-manifest/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp, open(dest, "wb") as out:
        out.write(resp.read())


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _run_runtime_info(python: str, extract_root: Path) -> dict[str, Any]:
    server = extract_root / "pointer_gpf" / "mcp" / "server.py"
    cmd = [
        python,
        str(server),
        "--tool",
        "get_mcp_runtime_info",
        "--args",
        "{}",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(extract_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {
                    "returncode": proc.returncode,
                    "stdout": out[:4000],
                    "stderr": err[:4000],
                },
                ensure_ascii=False,
            )
        )
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON from get_mcp_runtime_info: {out[:500]!r}") from exc
    if not parsed.get("ok"):
        raise RuntimeError(json.dumps(parsed, ensure_ascii=False))
    result = parsed.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("get_mcp_runtime_info result is not an object")
    return result


def main() -> int:
    manifest_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_MANIFEST
    report: dict[str, Any] = {"ok": False, "manifest": str(manifest_path)}

    try:
        if not manifest_path.is_file():
            report["error"] = f"manifest not found: {manifest_path}"
            print(json.dumps(report, ensure_ascii=False))
            return 2

        manifest = _load_manifest(manifest_path)
        url = _artifact_url(manifest)
        report["artifact_url"] = url
        expected = _expected_sha256(manifest)
        if expected:
            report["expected_sha256"] = expected

        with tempfile.TemporaryDirectory(prefix="pointer-gpf-artifact-") as tmp:
            tmp_path = Path(tmp)
            zip_path = tmp_path / "artifact.zip"
            try:
                _download(url, zip_path)
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                report["error"] = f"download failed: {exc}"
                print(json.dumps(report, ensure_ascii=False))
                return 1

            actual_hash = _sha256_file(zip_path)
            report["downloaded_sha256"] = actual_hash
            if expected and actual_hash != expected:
                report["error"] = "sha256 mismatch"
                report["expected_sha256"] = expected
                report["actual_sha256"] = actual_hash
                print(json.dumps(report, ensure_ascii=False))
                return 1

            with zipfile.ZipFile(zip_path, "r") as zf:
                names = _collect_zip_names(zf)
                missing = sorted(e for e in REQUIRED_ZIP_ENTRIES if e not in names)
                if missing:
                    report["error"] = "missing required zip entries"
                    report["missing_entries"] = missing
                    print(json.dumps(report, ensure_ascii=False))
                    return 1

                violations = _layout_violations(names)
                if violations:
                    report["error"] = "zip layout violates single-directory constraint"
                    report["layout_violations_sample"] = violations[:50]
                    print(json.dumps(report, ensure_ascii=False))
                    return 1

                extract_root = tmp_path / "extracted"
                extract_root.mkdir(parents=True, exist_ok=True)
                _safe_extract(zf, extract_root)

            try:
                runtime = _run_runtime_info(sys.executable, extract_root)
            except RuntimeError as exc:
                report["error"] = "get_mcp_runtime_info failed"
                report["details"] = str(exc)
                print(json.dumps(report, ensure_ascii=False))
                return 1

            tools = runtime.get("tools")
            if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
                report["error"] = "runtime info missing tools string list"
                print(json.dumps(report, ensure_ascii=False))
                return 1

            tool_set = set(tools)
            missing_tools = sorted(REQUIRED_TOOLS - tool_set)
            if missing_tools:
                report["error"] = "required tools missing from get_mcp_runtime_info"
                report["missing_tools"] = missing_tools
                report["tools_count"] = len(tools)
                print(json.dumps(report, ensure_ascii=False))
                return 1

            report["ok"] = True
            report["tools_count"] = len(tools)
            report["required_tools_ok"] = sorted(REQUIRED_TOOLS)
            print(json.dumps(report, ensure_ascii=False))
            return 0

    except ValueError as exc:
        report["error"] = str(exc)
        print(json.dumps(report, ensure_ascii=False))
        return 2
    except Exception as exc:  # pylint: disable=broad-except
        report["error"] = "unexpected error"
        report["details"] = str(exc)
        print(json.dumps(report, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
