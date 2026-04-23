import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_repro_flow import plan_bug_repro_flow


class BugReproFlowTests(unittest.TestCase):
    def _write_project_files(self, project_root: Path, flow_steps: list[dict[str, object]]) -> None:
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
            json.dumps({"flowId": "project_basicflow", "steps": flow_steps}, ensure_ascii=False),
            encoding="utf-8",
        )
        (project_root / "pointer_gpf" / "basicflow.meta.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-14T00:00:00+00:00",
                    "generation_summary": "summary",
                    "related_files": [
                        "project.godot",
                        "res://scenes/main_scene_example.tscn",
                        "res://scripts/main_menu_flow.gd",
                        "res://scenes/game_level.tscn",
                    ],
                    "project_file_summary": {
                        "total_file_count": 4,
                        "script_count": 1,
                        "scene_count": 2,
                    },
                    "last_successful_run_at": None,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _default_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            bug_report="点击开始游戏没有反应",
            bug_summary=None,
            expected_behavior="应该进入游戏关卡",
            steps_to_trigger="启动游戏|点击开始游戏",
            location_scene="res://scenes/main_scene_example.tscn",
            location_node="StartButton",
            location_script="res://scripts/main_menu_flow.gd",
            frequency_hint="always",
            severity_hint="core_progression_blocker",
            evidence_plan_json="",
            evidence_plan_file="",
        )

    def test_plan_bug_repro_flow_reuses_basicflow_and_appends_postconditions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_project_files(
                project_root,
                [
                    {"id": "launch_game", "action": "launchGame"},
                    {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                    {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                    {"id": "close_project", "action": "closeProject"},
                ],
            )

            payload = plan_bug_repro_flow(project_root, self._default_args())

        self.assertEqual(payload["schema"], "pointer_gpf.v2.repro_flow_plan.v1")
        self.assertEqual(payload["strategy"], "reuse_project_basicflow")
        self.assertTrue(payload["needs_flow_patch"])
        self.assertEqual(payload["candidate_flow"]["steps"][-1]["action"], "closeProject")
        self.assertTrue(
            any(str(step.get("id", "")).startswith("postcondition_") for step in payload["candidate_flow"]["steps"])
        )

    def test_plan_bug_repro_flow_inserts_missing_trigger_when_base_flow_has_no_click(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_project_files(
                project_root,
                [
                    {"id": "launch_game", "action": "launchGame"},
                    {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                    {"id": "close_project", "action": "closeProject"},
                ],
            )

            payload = plan_bug_repro_flow(project_root, self._default_args())

        steps = payload["candidate_flow"]["steps"]
        self.assertTrue(any(step.get("id") == "trigger_click_startbutton" for step in steps))
        contract = payload["execution_contract"]
        self.assertIn("trigger_click_startbutton", contract["trigger_step_ids"])

    def test_plan_bug_repro_flow_marks_existing_precondition_as_already_covered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_project_files(
                project_root,
                [
                    {"id": "launch_game", "action": "launchGame"},
                    {"id": "wait_startbutton", "action": "wait", "until": {"hint": "node_exists:StartButton"}},
                    {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                    {"id": "close_project", "action": "closeProject"},
                ],
            )

            payload = plan_bug_repro_flow(project_root, self._default_args())

        self.assertTrue(
            any(
                item["assertion_id"] == "interaction_target_present"
                and item["status"] == "already_covered_by_base_flow"
                for item in payload["assertion_coverage"]
            )
        )

    def test_plan_bug_repro_flow_builds_precondition_and_postcondition_execution_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_project_files(
                project_root,
                [
                    {"id": "launch_game", "action": "launchGame"},
                    {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                    {"id": "close_project", "action": "closeProject"},
                ],
            )

            payload = plan_bug_repro_flow(project_root, self._default_args())

        contract = payload["execution_contract"]
        self.assertIn("launch_game", contract["setup_step_ids"])
        self.assertIn("click_startbutton", contract["trigger_step_ids"])
        self.assertTrue(any(step_id.startswith("precondition_") for step_id in contract["precondition_step_ids"]))
        self.assertTrue(any(step_id.startswith("postcondition_") for step_id in contract["postcondition_step_ids"]))

    def test_plan_bug_repro_flow_inserts_model_evidence_steps_around_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_project_files(
                project_root,
                [
                    {"id": "launch_game", "action": "launchGame"},
                    {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                    {"id": "close_project", "action": "closeProject"},
                ],
            )
            args = self._default_args()
            args.evidence_plan_json = json.dumps(
                {
                    "steps": [
                        {
                            "id": "sample_startbutton_visible",
                            "phase": "post_trigger",
                            "action": "sample",
                            "target": {"hint": "node_name:StartButton"},
                            "metric": {"kind": "node_property", "property_path": "visible"},
                            "windowMs": 200,
                            "intervalMs": 50,
                            "evidenceKey": "startbutton_visible_window",
                        },
                        {
                            "id": "check_startbutton_visible_changed",
                            "phase": "final_check",
                            "action": "check",
                            "checkType": "node_property_changes_within_window",
                            "evidenceRef": "startbutton_visible_window",
                            "predicate": {"operator": "changed_from_baseline"},
                        },
                    ]
                }
            )

            payload = plan_bug_repro_flow(project_root, args)

        step_ids = [step["id"] for step in payload["candidate_flow"]["steps"]]
        self.assertEqual(payload["model_evidence_plan_status"], "accepted")
        self.assertEqual(payload["planned_runtime_evidence_step_count"], 2)
        self.assertIn("startbutton_visible_window", payload["evidence_refs_produced"])
        self.assertIn("startbutton_visible_window", payload["evidence_refs_required"])
        self.assertLess(step_ids.index("click_startbutton"), step_ids.index("sample_startbutton_visible"))
        self.assertLess(step_ids.index("sample_startbutton_visible"), step_ids.index("check_startbutton_visible_changed"))

    def test_plan_bug_repro_flow_blocks_rejected_evidence_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_project_files(
                project_root,
                [
                    {"id": "launch_game", "action": "launchGame"},
                    {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                    {"id": "close_project", "action": "closeProject"},
                ],
            )
            args = self._default_args()
            args.evidence_plan_json = json.dumps(
                {
                    "steps": [
                        {
                            "id": "sample_forever",
                            "action": "sample",
                            "target": {"hint": "node_name:Enemy"},
                            "metric": {"kind": "node_property", "property_path": "modulate"},
                            "windowMs": 999999,
                            "intervalMs": 50,
                            "evidenceKey": "enemy_modulate_window",
                        }
                    ]
                }
            )

            payload = plan_bug_repro_flow(project_root, args)

        self.assertEqual(payload["model_evidence_plan_status"], "rejected")
        self.assertEqual(payload["repro_readiness"], "blocked_by_rejected_evidence_plan")
        self.assertTrue(payload["rejected_evidence_plan_reasons"])

    def test_plan_bug_repro_flow_expands_trigger_window_observe_around_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_project_files(
                project_root,
                [
                    {"id": "launch_game", "action": "launchGame"},
                    {"id": "click_startbutton", "action": "click", "target": {"hint": "node_name:StartButton"}},
                    {"id": "close_project", "action": "closeProject"},
                ],
            )
            args = self._default_args()
            args.evidence_plan_json = json.dumps(
                {
                    "steps": [
                        {
                            "id": "observe_scene_change",
                            "phase": "trigger_window",
                            "action": "observe",
                            "event": {"kind": "scene_changed"},
                            "windowMs": 1000,
                            "evidenceKey": "scene_change_window",
                        },
                        {
                            "id": "check_scene_change_event",
                            "phase": "final_check",
                            "action": "check",
                            "checkType": "scene_changed_event",
                            "evidenceRef": "scene_change_window",
                            "predicate": {"operator": "event_count_at_least", "count": 1},
                        },
                    ]
                }
            )

            payload = plan_bug_repro_flow(project_root, args)

        step_ids = [step["id"] for step in payload["candidate_flow"]["steps"]]
        self.assertEqual(payload["model_evidence_plan_status"], "accepted")
        self.assertLess(step_ids.index("observe_scene_change_start"), step_ids.index("click_startbutton"))
        self.assertLess(step_ids.index("click_startbutton"), step_ids.index("observe_scene_change_collect"))
        self.assertLess(step_ids.index("observe_scene_change_collect"), step_ids.index("check_scene_change_event"))
        self.assertIn("scene_change_window", payload["evidence_refs_produced"])
        self.assertIn("scene_change_window", payload["evidence_refs_required"])


if __name__ == "__main__":
    unittest.main()
