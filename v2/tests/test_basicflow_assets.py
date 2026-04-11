import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.basicflow_assets import (
    BasicFlowAssetError,
    basicflow_exists,
    basicflow_paths,
    build_basicflow_metadata,
    compute_project_file_summary,
    load_basicflow_assets,
    mark_basicflow_run_success,
    save_basicflow_assets,
    validate_basicflow_metadata,
)


def _sample_flow() -> dict[str, object]:
    return {
        "flowId": "basic",
        "steps": [
            {"id": "launch", "action": "launchGame"},
            {"id": "close", "action": "closeProject"},
        ],
    }


class BasicFlowAssetTests(unittest.TestCase):
    def test_save_and_load_basicflow_assets_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            metadata = build_basicflow_metadata(
                generation_summary="Launch the project and prove it can enter play mode.",
                related_files=["project.godot", "scenes/main.tscn"],
                project_file_summary={"total_file_count": 3, "script_count": 1, "scene_count": 1},
            )

            paths = save_basicflow_assets(project_root, _sample_flow(), metadata)
            loaded = load_basicflow_assets(project_root)
            flow_exists = paths.flow_file.is_file()
            meta_exists = paths.meta_file.is_file()

        self.assertTrue(flow_exists)
        self.assertTrue(meta_exists)
        self.assertEqual(loaded["flow"]["flowId"], "basic")
        self.assertEqual(loaded["meta"]["generation_summary"], metadata["generation_summary"])
        self.assertIsNone(loaded["meta"]["last_successful_run_at"])

    def test_validate_basicflow_metadata_rejects_missing_related_files(self) -> None:
        with self.assertRaises(BasicFlowAssetError):
            validate_basicflow_metadata(
                {
                    "generated_at": "2026-04-11T00:00:00+00:00",
                    "generation_summary": "summary",
                    "project_file_summary": {"total_file_count": 1, "script_count": 0, "scene_count": 0},
                    "last_successful_run_at": None,
                }
            )

    def test_compute_project_file_summary_counts_files_scripts_and_scenes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text("[application]\nconfig/name=\"tmp\"\n", encoding="utf-8")
            (project_root / "player.gd").write_text("extends Node\n", encoding="utf-8")
            (project_root / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")
            (project_root / "README.txt").write_text("hello\n", encoding="utf-8")
            (project_root / "pointer_gpf").mkdir(parents=True, exist_ok=True)
            (project_root / "pointer_gpf" / "basicflow.json").write_text("{}", encoding="utf-8")
            (project_root / "pointer_gpf" / "tmp").mkdir(parents=True, exist_ok=True)
            (project_root / "pointer_gpf" / "tmp" / "runtime_gate.json").write_text("{}", encoding="utf-8")

            summary = compute_project_file_summary(project_root)

        self.assertEqual(summary["total_file_count"], 4)
        self.assertEqual(summary["script_count"], 1)
        self.assertEqual(summary["scene_count"], 1)

    def test_mark_basicflow_run_success_updates_only_timestamp_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            metadata = build_basicflow_metadata(
                generation_summary="summary",
                related_files=["project.godot"],
                project_file_summary={"total_file_count": 1, "script_count": 0, "scene_count": 0},
            )
            save_basicflow_assets(project_root, _sample_flow(), metadata)

            updated_meta = mark_basicflow_run_success(project_root, success_at="2026-04-11T12:00:00+00:00")
            loaded = load_basicflow_assets(project_root)

        self.assertEqual(updated_meta["last_successful_run_at"], "2026-04-11T12:00:00+00:00")
        self.assertEqual(loaded["meta"]["last_successful_run_at"], "2026-04-11T12:00:00+00:00")
        self.assertEqual(loaded["meta"]["generation_summary"], "summary")
        self.assertEqual(loaded["meta"]["related_files"], ["project.godot"])

    def test_basicflow_exists_requires_both_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            paths = basicflow_paths(project_root)
            paths.flow_file.parent.mkdir(parents=True, exist_ok=True)
            paths.flow_file.write_text(json.dumps(_sample_flow()), encoding="utf-8")

            exists_before = basicflow_exists(project_root)

            paths.meta_file.write_text(
                json.dumps(
                    build_basicflow_metadata(
                        generation_summary="summary",
                        related_files=["project.godot"],
                        project_file_summary={"total_file_count": 1, "script_count": 0, "scene_count": 0},
                    )
                ),
                encoding="utf-8",
            )
            exists_after = basicflow_exists(project_root)

        self.assertFalse(exists_before)
        self.assertTrue(exists_after)

    def test_save_basicflow_assets_rejects_invalid_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            metadata = build_basicflow_metadata(
                generation_summary="summary",
                related_files=["project.godot"],
                project_file_summary={"total_file_count": 1, "script_count": 0, "scene_count": 0},
            )

            with self.assertRaises(BasicFlowAssetError):
                save_basicflow_assets(
                    project_root,
                    {"flowId": "bad", "steps": [{"id": "bad", "action": "unsupported"}]},
                    metadata,
                )


if __name__ == "__main__":
    unittest.main()
