#!/usr/bin/env python3
"""Hard-rule UI checker for exported ui_spec."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    passed: bool
    failures: list[dict[str, Any]]


def load_spec(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_hard_check(ui_spec: dict[str, Any], rules: dict[str, Any]) -> CheckResult:
    controls = list(ui_spec.get("controls", []))
    by_test_id = {c.get("meta_test_id", ""): c for c in controls if c.get("meta_test_id")}
    failures: list[dict[str, Any]] = []

    # Required nodes must exist and be visible.
    for test_id in rules.get("required_visible", []):
        node = by_test_id.get(test_id)
        if not node:
            failures.append({"type": "missing_node", "test_id": test_id})
            continue
        if not bool(node.get("visible", False)):
            failures.append({"type": "not_visible", "test_id": test_id})

    # Size checks.
    for item in rules.get("size_equals", []):
        test_id = item.get("test_id", "")
        node = by_test_id.get(test_id)
        if not node:
            failures.append({"type": "missing_node", "test_id": test_id})
            continue
        expected = item.get("size", [0, 0])
        actual = node.get("size", [0, 0])
        tolerance = float(item.get("tolerance", 0.0))
        if (
            abs(float(actual[0]) - float(expected[0])) > tolerance
            or abs(float(actual[1]) - float(expected[1])) > tolerance
        ):
            failures.append(
                {
                    "type": "size_mismatch",
                    "test_id": test_id,
                    "expected": expected,
                    "actual": actual,
                    "tolerance": tolerance,
                }
            )

    return CheckResult(passed=len(failures) == 0, failures=failures)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run hard UI check")
    parser.add_argument("--spec", required=True, help="Path to ui_spec json")
    parser.add_argument("--rules", required=True, help="Path to hard rule json")
    parser.add_argument("--output", required=True, help="Output result path")
    args = parser.parse_args()

    spec = load_spec(Path(args.spec).resolve())
    rules = load_spec(Path(args.rules).resolve())
    result = run_hard_check(spec, rules)
    payload = {"passed": result.passed, "failures": result.failures}
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
