#!/usr/bin/env python3
"""Run a quick regression suite and generate a summary report.

Suite cases:
1) exploration_smoke should pass
2) visual_regression_probe baseline record should pass
3) visual_regression_probe check should fail with visual_regression (canary)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from runner import GameTestRunner, RunRequest, RunResult


def _utc_now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _case_record(name: str, result: RunResult, expected: str, ok: bool, note: str = "") -> dict:
    return {
        "name": name,
        "expected": expected,
        "actual_status": result.status,
        "actual_failure_category": result.failure_category,
        "ok": ok,
        "note": note,
        "run_id": result.run_id,
        "artifact_root": result.artifact_root,
    }


def run_suite(project_root: Path, godot_bin: str, timeout_sec: int) -> tuple[dict, int]:
    runner = GameTestRunner(project_root=project_root)
    cases: list[dict] = []

    # Case 1: exploration smoke should pass.
    r1 = runner.run(
        RunRequest(
            system="exploration",
            project_root=project_root,
            scenario="exploration_smoke",
            timeout_sec=timeout_sec,
            godot_bin=godot_bin,
            dry_run=False,
        )
    )
    cases.append(_case_record("exploration_smoke", r1, "finished", r1.status == "finished"))

    # Case 2: visual baseline record should pass.
    r2 = runner.run(
        RunRequest(
            system="visual",
            project_root=project_root,
            scenario="visual_regression_probe",
            timeout_sec=timeout_sec,
            godot_bin=godot_bin,
            extra_args=["--record-baseline"],
            dry_run=False,
        )
    )
    cases.append(_case_record("visual_record_baseline", r2, "finished", r2.status == "finished"))

    # Case 3: visual check should fail with visual_regression (canary behavior).
    r3 = runner.run(
        RunRequest(
            system="visual",
            project_root=project_root,
            scenario="visual_regression_probe",
            timeout_sec=timeout_sec,
            godot_bin=godot_bin,
            dry_run=False,
        )
    )
    ok3 = r3.status != "finished" and r3.failure_category == "visual_regression"
    cases.append(
        _case_record(
            "visual_check_canary",
            r3,
            "failed + visual_regression",
            ok3,
            "This case is expected to fail to prove visual regression detection.",
        )
    )

    suite_status = "passed" if all(c["ok"] for c in cases) else "failed"
    suite_id = f"{_utc_now_id()}_quick_regression_suite"
    suite_root = project_root / "artifacts" / "test-suites" / suite_id
    suite_root.mkdir(parents=True, exist_ok=True)

    summary = {
        "suite_id": suite_id,
        "status": suite_status,
        "project_root": str(project_root),
        "cases": cases,
    }
    (suite_root / "suite_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Quick Regression Suite",
        "",
        f"- suite_id: `{suite_id}`",
        f"- status: `{suite_status}`",
        "",
        "## Cases",
    ]
    for c in cases:
        lines.append(
            f"- `{c['name']}` expected `{c['expected']}`, got `{c['actual_status']}` / `{c['actual_failure_category']}` -> `{c['ok']}`"
        )
        lines.append(f"  - run_id: `{c['run_id']}`")
        lines.append(f"  - artifact_root: `{c['artifact_root']}`")
        if c["note"]:
            lines.append(f"  - note: {c['note']}")
    (suite_root / "suite_report.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return summary, (0 if suite_status == "passed" else 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run quick regression suite.")
    parser.add_argument("--project-root", required=True, help="Project root path")
    parser.add_argument("--godot-bin", required=True, help="Godot executable path")
    parser.add_argument("--timeout-sec", type=int, default=120)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary, code = run_suite(
        project_root=Path(args.project_root).resolve(),
        godot_bin=args.godot_bin,
        timeout_sec=args.timeout_sec,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
