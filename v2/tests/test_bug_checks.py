import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_checks import build_executable_checks, define_bug_checks, summarize_check_results


class BugChecksTests(unittest.TestCase):
    def test_define_bug_checks_returns_mapped_runtime_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '\n'.join(
                    [
                        "[application]",
                        'run/main_scene="res://scenes/main_scene_example.tscn"',
                    ]
                ),
                encoding="utf-8",
            )
            (project_root / "pointer_gpf").mkdir(parents=True, exist_ok=True)
            (project_root / "pointer_gpf" / "basicflow.json").write_text(
                json.dumps(
                    {
                        "flowId": "project_basicflow",
                        "steps": [
                            {"id": "launch_game", "action": "launchGame"},
                            {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                            {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                            {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                            {"id": "check_startbutton_hidden", "action": "check", "hint": "node_hidden:StartButton"},
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (project_root / "pointer_gpf" / "basicflow.meta.json").write_text(
                json.dumps({"related_files": ["res://scripts/main_menu_flow.gd"]}, ensure_ascii=False),
                encoding="utf-8",
            )

            args = argparse.Namespace(
                bug_report="点击开始游戏后没有进入关卡",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|点击开始游戏",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
                bug_case_file="",
            )

            payload = define_bug_checks(project_root, args)

        self.assertEqual(payload["schema"], "pointer_gpf.v2.check_set.v1")
        self.assertTrue(any(item["source_assertion_id"] == "interaction_target_present" for item in payload["checks"]))
        self.assertTrue(all(str(item["mapped_step_id"]).strip() for item in payload["checks"]))

    def test_summarize_check_results_marks_failed_and_not_run_checks(self) -> None:
        candidate_flow = {
            "steps": [
                {"id": "launch_game", "action": "launchGame"},
                {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                {"id": "wait_gamelevel", "action": "wait", "until": {"hint": "node_exists:GameLevel"}},
                {"id": "check_pointerhud", "action": "check", "hint": "node_exists:GamePointerHud"},
            ]
        }
        checks = [
            {
                "check_id": "precondition_check_0",
                "source_assertion_id": "interaction_target_present",
                "stage": "precondition",
                "kind": "runtime_hint",
                "action": "wait",
                "hint": "node_exists:StartButton",
                "mapped_step_id": "wait_startbutton",
            },
            {
                "check_id": "postcondition_check_0",
                "source_assertion_id": "target_scene_reached",
                "stage": "postcondition",
                "kind": "scene_active",
                "action": "wait",
                "hint": "node_exists:GameLevel",
                "mapped_step_id": "wait_gamelevel",
            },
            {
                "check_id": "postcondition_check_1",
                "source_assertion_id": "hud_present",
                "stage": "postcondition",
                "kind": "runtime_hint",
                "action": "check",
                "hint": "node_exists:GamePointerHud",
                "mapped_step_id": "check_pointerhud",
            },
        ]

        payload = summarize_check_results(
            candidate_flow,
            checks,
            run_ok=False,
            failed_step_id="wait_gamelevel",
            failure_status="bug_reproduced",
            error_code="TIMEOUT",
            error_message="target scene never appeared",
        )

        self.assertEqual(payload["summary"]["failed_check_ids"], ["postcondition_check_0"])
        self.assertEqual(payload["results"][0]["status"], "passed")
        self.assertEqual(payload["results"][1]["status"], "failed")
        self.assertEqual(payload["results"][2]["status"], "not_run")

    def test_build_executable_checks_preserves_structured_runtime_check(self) -> None:
        assertion_set = {
            "postconditions": [
                {
                    "id": "visible_state_changed",
                    "kind": "runtime_evidence",
                    "target": {"hint": "node_name:Enemy"},
                    "expected": True,
                    "reason": "model requested a generic sampled-state check",
                    "runtime_check": {
                        "supported": True,
                        "action": "check",
                        "check_type": "node_property_changes_within_window",
                        "target": {"hint": "node_name:Enemy"},
                        "metric": {"kind": "node_property", "property_path": "modulate"},
                        "sample_plan": {"window_ms": 400, "interval_ms": 50},
                        "predicate": {"operator": "not_equals", "compare_to": "baseline_first_sample"},
                        "evidence_ref": "enemy_modulate_window",
                    },
                }
            ]
        }
        candidate_flow = {
            "steps": [
                {
                    "id": "check_enemy_modulate_changed",
                    "action": "check",
                    "checkType": "node_property_changes_within_window",
                    "evidenceRef": "enemy_modulate_window",
                }
            ]
        }

        checks = build_executable_checks(assertion_set, candidate_flow)

        self.assertEqual(checks[0]["check_type"], "node_property_changes_within_window")
        self.assertEqual(checks[0]["metric"]["property_path"], "modulate")
        self.assertEqual(checks[0]["predicate"]["operator"], "not_equals")
        self.assertEqual(checks[0]["evidence_ref"], "enemy_modulate_window")
        self.assertEqual(checks[0]["mapped_step_id"], "check_enemy_modulate_changed")

    def test_build_executable_checks_includes_model_evidence_plan_check_step(self) -> None:
        candidate_flow = {
            "steps": [
                {
                    "id": "check_enemy_modulate_changed",
                    "action": "check",
                    "source": "model_evidence_plan",
                    "phase": "final_check",
                    "checkType": "node_property_changes_within_window",
                    "evidenceRef": "enemy_modulate_window",
                    "predicate": {"operator": "changed_from_baseline"},
                }
            ]
        }

        checks = build_executable_checks({"preconditions": [], "postconditions": []}, candidate_flow)

        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["source_assertion_id"], "model_evidence_plan")
        self.assertEqual(checks[0]["evidence_ref"], "enemy_modulate_window")
        self.assertEqual(checks[0]["mapped_step_id"], "check_enemy_modulate_changed")


if __name__ == "__main__":
    unittest.main()
