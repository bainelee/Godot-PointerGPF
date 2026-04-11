import tempfile
import time
import unittest
from pathlib import Path

from v2.mcp_core.basicflow_assets import build_basicflow_metadata, save_basicflow_assets
from v2.mcp_core.basicflow_staleness import detect_basicflow_staleness


def _sample_flow() -> dict[str, object]:
    return {
        "flowId": "basic",
        "steps": [
            {"id": "launch", "action": "launchGame"},
            {"id": "close", "action": "closeProject"},
        ],
    }


class BasicFlowStalenessTests(unittest.TestCase):
    def test_detect_basicflow_staleness_returns_missing_when_assets_do_not_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)

            result = detect_basicflow_staleness(project_root)

        self.assertEqual(result["status"], "missing")
        self.assertFalse(result["is_stale"])

    def test_detect_basicflow_staleness_is_fresh_when_related_files_and_summary_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="scenes/main.tscn"\n',
                encoding="utf-8",
            )
            (project_root / "scenes").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")
            generated_at = "2030-01-01T00:00:00+00:00"
            metadata = build_basicflow_metadata(
                generation_summary="summary",
                related_files=["project.godot"],
                project_file_summary={"total_file_count": 2, "script_count": 0, "scene_count": 1},
                generated_at=generated_at,
            )
            save_basicflow_assets(project_root, _sample_flow(), metadata)

            result = detect_basicflow_staleness(project_root)

        self.assertEqual(result["status"], "fresh")
        self.assertFalse(result["is_stale"])
        self.assertEqual(result["reasons"], [])

    def test_detect_basicflow_staleness_reports_missing_related_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            generated_at = "2030-01-01T00:00:00+00:00"
            metadata = build_basicflow_metadata(
                generation_summary="summary",
                related_files=["scenes/main.tscn"],
                project_file_summary={"total_file_count": 0, "script_count": 0, "scene_count": 0},
                generated_at=generated_at,
            )
            save_basicflow_assets(project_root, _sample_flow(), metadata)

            result = detect_basicflow_staleness(project_root)

        self.assertEqual(result["status"], "stale")
        self.assertTrue(result["is_stale"])
        self.assertEqual(result["reasons"][0]["code"], "BASICFLOW_RELATED_FILE_MISSING")

    def test_detect_basicflow_staleness_reports_related_file_changed_after_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            related = project_root / "project.godot"
            related.write_text("[application]\n", encoding="utf-8")
            metadata = build_basicflow_metadata(
                generation_summary="summary",
                related_files=["project.godot"],
                project_file_summary={"total_file_count": 1, "script_count": 0, "scene_count": 0},
                generated_at="2000-01-01T00:00:00+00:00",
            )
            save_basicflow_assets(project_root, _sample_flow(), metadata)
            time.sleep(0.02)
            related.write_text("[application]\nconfig/name=\"changed\"\n", encoding="utf-8")

            result = detect_basicflow_staleness(project_root)

        self.assertEqual(result["status"], "stale")
        self.assertTrue(any(item["code"] == "BASICFLOW_RELATED_FILE_CHANGED" for item in result["reasons"]))

    def test_detect_basicflow_staleness_accepts_res_scheme_related_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="res://scenes/main.tscn"\n',
                encoding="utf-8",
            )
            (project_root / "scenes").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")
            metadata = build_basicflow_metadata(
                generation_summary="summary",
                related_files=["res://scenes/main.tscn"],
                project_file_summary={"total_file_count": 2, "script_count": 0, "scene_count": 1},
                generated_at="2030-01-01T00:00:00+00:00",
            )
            save_basicflow_assets(project_root, _sample_flow(), metadata)

            result = detect_basicflow_staleness(project_root)

        self.assertEqual(result["status"], "fresh")
        self.assertFalse(result["is_stale"])

    def test_detect_basicflow_staleness_reports_broad_project_summary_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text("[application]\n", encoding="utf-8")
            metadata = build_basicflow_metadata(
                generation_summary="summary",
                related_files=["project.godot"],
                project_file_summary={"total_file_count": 1, "script_count": 0, "scene_count": 0},
                generated_at="2030-01-01T00:00:00+00:00",
            )
            save_basicflow_assets(project_root, _sample_flow(), metadata)
            (project_root / "a.gd").write_text("extends Node\n", encoding="utf-8")

            result = detect_basicflow_staleness(project_root)

        self.assertEqual(result["status"], "stale")
        self.assertTrue(any(item["code"] == "BASICFLOW_PROJECT_FILE_SUMMARY_CHANGED" for item in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
