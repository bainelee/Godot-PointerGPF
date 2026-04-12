from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_regression_module():
    path = _repo_root() / "scripts" / "verify-v2-regression.py"
    spec = importlib.util.spec_from_file_location("verify_v2_regression", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load regression helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fixed V2 isolated-runtime validation bundle.")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    helper = _load_regression_module()
    project_root = Path(args.project_root).resolve()
    results = [
        helper.run_isolated_runtime_flow(project_root, "basic_minimal_flow.json"),
        helper.run_isolated_runtime_flow(project_root, "basic_interactive_flow.json"),
    ]
    ok = all(item.get("ok", False) for item in results)
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
