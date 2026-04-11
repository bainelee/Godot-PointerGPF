import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.basicflow_assets import build_basicflow_metadata, save_basicflow_assets
from v2.mcp_core.basicflow_staleness import analyze_basicflow_staleness


def _sample_flow() -> dict[str, object]:
    return {
        "flowId": "project_basicflow",
        "steps": [
            {"id": "launch", "action": "launchGame"},
            {"id": "close", "action": "closeProject"},
        ],
    }


class BasicFlowAnalysisTests(unittest.TestCase):
    def test_analyze_basicflow_staleness_returns_missing_summary_when_assets_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_basicflow_staleness(Path(tmp))

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["recommended_next_step"], "generate_basic_flow")

    def test_analyze_basicflow_staleness_returns_fresh_summary(self) -> None:
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
                related_files=["project.godot", "res://scenes/main.tscn"],
                project_file_summary={"total_file_count": 2, "script_count": 0, "scene_count": 1},
                generated_at="2030-01-01T00:00:00+00:00",
            )
            save_basicflow_assets(project_root, _sample_flow(), metadata)

            result = analyze_basicflow_staleness(project_root)

        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["recommended_next_step"], "run_basic_flow")
        self.assertEqual(result["flow_summary"], "summary")

    def test_analyze_basicflow_staleness_returns_stale_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text("[application]\n", encoding="utf-8")
            metadata = build_basicflow_metadata(
                generation_summary="summary",
                related_files=["project.godot"],
                project_file_summary={"total_file_count": 1, "script_count": 0, "scene_count": 0},
                generated_at="2000-01-01T00:00:00+00:00",
            )
            save_basicflow_assets(project_root, _sample_flow(), metadata)
            (project_root / "project.godot").write_text("[application]\nconfig/name=\"changed\"\n", encoding="utf-8")

            result = analyze_basicflow_staleness(project_root)

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["recommended_next_step"], "regenerate_basicflow_or_run_with_allow_stale")
        self.assertTrue(result["reasons"])
