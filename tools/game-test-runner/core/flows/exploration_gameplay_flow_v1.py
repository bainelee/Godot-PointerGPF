#!/usr/bin/env python3
"""First real gameplay debug flow template.

This template intentionally keeps scope small and stable:
- Reuse exploration smoke scene as the first executable gameplay probe.
- Add explicit wait/verify steps around generated artifacts for debugging.
"""

from __future__ import annotations


FLOW_ID = "exploration_gameplay_flow_v1"


def get_flow_definition() -> dict:
    return {
        "flow_id": FLOW_ID,
        "name": "Exploration Gameplay Flow v1",
        "description": "Run exploration gameplay template with step markers and evidence checks.",
        "steps": [
            {
                "name": "run_exploration_gameplay_scene",
                "type": "run_scenario",
                "system": "exploration",
                "scenario": "exploration_gameplay_flow_test",
                "screenshot_prefix": "flow_exploration_",
                "wait_condition": {
                    "type": "process_exit",
                    "description": "Godot process exits within timeout.",
                },
                "assertions": [
                    {"type": "run_status_equals", "expected": "finished"},
                    {"type": "run_exit_code_equals", "expected": 0},
                ],
            },
            {
                "name": "assert_gameplay_markers",
                "type": "assert_log_markers",
                "path": "logs/stdout.log",
                "markers": [
                    "[GameplayFlowV1] STEP bootstrap PASS",
                    "[GameplayFlowV1] STEP enter_exploration_map PASS",
                    "[GameplayFlowV1] STEP execute_exploration_action PASS",
                    "[GameplayFlowV1] FLOW PASS",
                ],
                "wait_condition": {
                    "type": "log_markers_present",
                    "description": "stdout contains gameplay flow step markers.",
                },
            },
            {
                "name": "wait_for_run_report_file",
                "type": "wait_for_file",
                "path": "report.json",
                "timeout_sec": 5,
                "poll_interval_sec": 0.2,
                "wait_condition": {
                    "type": "file_exists",
                    "description": "report.json is materialized in artifact root.",
                },
                "assertions": [{"type": "file_exists", "path": "report.json"}],
            },
            {
                "name": "verify_debug_evidence",
                "type": "assert_files",
                "wait_condition": {
                    "type": "artifacts_ready",
                    "description": "stdout/stderr logs and run metadata are readable.",
                },
                "assertions": [
                    {"type": "file_exists", "path": "run_meta.json"},
                    {"type": "file_exists", "path": "logs/stdout.log"},
                    {"type": "file_exists", "path": "logs/stderr.log"},
                    {"type": "file_exists", "path": "screenshots/flow_exploration_step_01_bootstrap.png"},
                    {"type": "file_exists", "path": "screenshots/flow_exploration_step_02_enter_map.png"},
                    {"type": "file_exists", "path": "screenshots/flow_exploration_step_03_explore_action.png"},
                ],
            },
            {
                "name": "assert_step_screenshots_distinct",
                "type": "assert_files_distinct",
                "files": [
                    "screenshots/flow_exploration_step_01_bootstrap.png",
                    "screenshots/flow_exploration_step_02_enter_map.png",
                    "screenshots/flow_exploration_step_03_explore_action.png",
                ],
                "wait_condition": {
                    "type": "visual_step_variation",
                    "description": "Step screenshots should not be byte-identical.",
                },
            },
        ],
    }

