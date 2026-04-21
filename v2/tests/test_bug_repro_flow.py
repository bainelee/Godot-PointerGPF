import argparse
import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.bug_repro_flow import plan_bug_repro_flow


class BugReproFlowTests(unittest.TestCase):
    def test_plan_bug_repro_flow_reuses_basicflow_and_appends_assertions(self) -> None:
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
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
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
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|点击开始游戏",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        self.assertEqual(payload["schema"], "pointer_gpf.v2.repro_flow_plan.v1")
        self.assertEqual(payload["strategy"], "reuse_project_basicflow")
        self.assertTrue(payload["needs_flow_patch"])
        self.assertGreaterEqual(payload["planned_assertion_step_count"], 1)
        self.assertEqual(payload["candidate_flow"]["steps"][-1]["action"], "closeProject")

    def test_plan_bug_repro_flow_adds_direct_state_change_assertion_step_when_target_scene_is_already_checked(self) -> None:
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
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
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
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|点击开始游戏",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        self.assertNotIn("interaction_should_change_state", payload["unsupported_assertions"])
        self.assertEqual(payload["repro_readiness"], "ready_for_repro_run")
        self.assertGreaterEqual(payload["planned_assertion_step_count"], 1)
        self.assertTrue(
            any(
                item["assertion_id"] == "interaction_should_change_state"
                and item["status"] == "covered_by_planned_step"
                for item in payload["assertion_coverage"]
            )
        )
        self.assertTrue(
            any(
                str(step.get("id", "")).startswith("assert_")
                and (
                    str(step.get("hint", "")).strip() == "node_exists:GameLevel"
                    or str(step.get("until", {}).get("hint", "")).strip() == "node_exists:GameLevel"
                )
                for step in payload["candidate_flow"]["steps"]
            )
        )

    def test_plan_bug_repro_flow_inserts_post_click_settle_delay_for_trigger_refinement(self) -> None:
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
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
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
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|点击开始游戏",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        steps = payload["candidate_flow"]["steps"]
        click_index = next(index for index, step in enumerate(steps) if step.get("id") == "click_startbutton")
        delay_step = steps[click_index + 1]
        self.assertEqual(delay_step["action"], "delay")
        self.assertEqual(delay_step["timeoutMs"], 250)
        self.assertTrue(str(delay_step["id"]).startswith("tighten_trigger_after_click"))

    def test_plan_bug_repro_flow_inserts_pre_click_wait_from_steps_to_trigger(self) -> None:
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
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
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
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|等待主菜单|点击开始游戏",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        steps = payload["candidate_flow"]["steps"]
        click_index = next(index for index, step in enumerate(steps) if step.get("id") == "click_startbutton")
        delay_step = steps[click_index - 1]
        self.assertEqual(delay_step["action"], "delay")
        self.assertEqual(delay_step["timeoutMs"], 400)
        self.assertTrue(str(delay_step["id"]).startswith("trigger_wait_before_click"))

    def test_plan_bug_repro_flow_adds_hidden_start_button_assertion_step(self) -> None:
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
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
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
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|点击开始游戏",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        self.assertTrue(
            any(
                str(step.get("hint", "")).strip() == "node_hidden:StartButton"
                or str(step.get("until", {}).get("hint", "")).strip() == "node_hidden:StartButton"
                for step in payload["candidate_flow"]["steps"]
            )
        )

    def test_plan_bug_repro_flow_inserts_repeat_click_from_steps_to_trigger(self) -> None:
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
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
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
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|点击开始游戏|再次点击开始游戏",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        steps = payload["candidate_flow"]["steps"]
        click_indices = [index for index, step in enumerate(steps) if step.get("action") == "click"]
        self.assertGreaterEqual(len(click_indices), 2)
        second_click = steps[click_indices[1]]
        self.assertTrue(str(second_click["id"]).startswith("trigger_repeat_click"))
        self.assertEqual(second_click["target"]["hint"], "node_name:StartButton")

    def test_plan_bug_repro_flow_inserts_post_launch_delay_from_steps_to_trigger(self) -> None:
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
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
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
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|等待主菜单|点击开始游戏",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        steps = payload["candidate_flow"]["steps"]
        launch_index = next(index for index, step in enumerate(steps) if step.get("id") == "launch_game")
        delay_step = steps[launch_index + 1]
        self.assertEqual(delay_step["action"], "delay")
        self.assertEqual(delay_step["timeoutMs"], 600)
        self.assertTrue(str(delay_step["id"]).startswith("trigger_wait_after_launch"))

    def test_plan_bug_repro_flow_inserts_scene_checkpoint_from_steps_to_trigger(self) -> None:
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
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
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
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡",
                steps_to_trigger="启动游戏|点击开始游戏|进入游戏关卡",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        steps = payload["candidate_flow"]["steps"]
        checkpoint_indices = [
            index
            for index, step in enumerate(steps)
            if str(step.get("id", "")).startswith("trigger_scene_checkpoint")
            and step.get("action") == "check"
            and step.get("hint") == "node_exists:GameLevel"
        ]
        self.assertEqual(len(checkpoint_indices), 1)
        wait_index = next(index for index, step in enumerate(steps) if step.get("id") == "wait_gamelevel")
        self.assertGreater(checkpoint_indices[0], wait_index)

    def test_plan_bug_repro_flow_inserts_ui_checkpoint_from_steps_to_trigger(self) -> None:
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
                            {"id": "check_gamepointerhud", "action": "check", "hint": "node_exists:GamePointerHud"},
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
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
                            "res://scenes/ui/game_pointer_hud.tscn",
                        ],
                        "project_file_summary": {
                            "total_file_count": 5,
                            "script_count": 1,
                            "scene_count": 3,
                        },
                        "last_successful_run_at": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                bug_report="点击开始游戏没有反应",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡并显示HUD",
                steps_to_trigger="启动游戏|点击开始游戏|显示HUD",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        steps = payload["candidate_flow"]["steps"]
        checkpoint_indices = [
            index
            for index, step in enumerate(steps)
            if str(step.get("id", "")).startswith("trigger_ui_checkpoint")
            and step.get("action") == "check"
            and step.get("hint") == "node_exists:GamePointerHud"
        ]
        self.assertEqual(len(checkpoint_indices), 1)
        hud_index = next(index for index, step in enumerate(steps) if step.get("id") == "check_gamepointerhud")
        self.assertGreater(checkpoint_indices[0], hud_index)

    def test_plan_bug_repro_flow_inserts_hidden_ui_checkpoint_from_steps_to_trigger(self) -> None:
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
                            {"id": "check_gamepointerhud", "action": "check", "hint": "node_exists:GamePointerHud"},
                            {"id": "close_project", "action": "closeProject"},
                        ],
                    },
                    ensure_ascii=False,
                ),
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
                            "res://scenes/ui/game_pointer_hud.tscn",
                        ],
                        "project_file_summary": {
                            "total_file_count": 5,
                            "script_count": 1,
                            "scene_count": 3,
                        },
                        "last_successful_run_at": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                bug_report="点击开始游戏后HUD不该继续显示",
                bug_summary=None,
                expected_behavior="应该进入游戏关卡并隐藏HUD",
                steps_to_trigger="启动游戏|点击开始游戏|关闭HUD",
                location_scene="res://scenes/main_scene_example.tscn",
                location_node="StartButton",
                location_script="res://scripts/main_menu_flow.gd",
                frequency_hint="always",
                severity_hint="core_progression_blocker",
            )

            payload = plan_bug_repro_flow(project_root, args)

        steps = payload["candidate_flow"]["steps"]
        checkpoint_indices = [
            index
            for index, step in enumerate(steps)
            if str(step.get("id", "")).startswith("trigger_ui_hidden_checkpoint")
            and step.get("action") == "check"
            and step.get("hint") == "node_hidden:GamePointerHud"
        ]
        self.assertEqual(len(checkpoint_indices), 1)
        hud_index = next(index for index, step in enumerate(steps) if step.get("id") == "check_gamepointerhud")
        self.assertGreater(checkpoint_indices[0], hud_index)
        self.assertFalse(
            any(str(step.get("id", "")).startswith("trigger_ui_checkpoint") for step in steps)
        )


if __name__ == "__main__":
    unittest.main()
