import base64
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ONE_BY_ONE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2r8lUAAAAASUVORK5CYII="
)


def _run_tool(repo_root: Path, tool: str, args: dict) -> dict:
    cmd = [
        "python",
        str(repo_root / "mcp" / "server.py"),
        "--tool",
        tool,
        "--args",
        json.dumps(args, ensure_ascii=False),
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError(f"tool {tool} failed: {proc.stdout}\n{proc.stderr}")
    payload = json.loads(proc.stdout)
    if not payload.get("ok"):
        raise AssertionError(f"tool {tool} returned error: {json.dumps(payload, ensure_ascii=False)}")
    return payload["result"]


def _run_tool_raw(repo_root: Path, tool: str, args: dict) -> tuple[int, dict]:
    cmd = [
        "python",
        str(repo_root / "mcp" / "server.py"),
        "--tool",
        tool,
        "--args",
        json.dumps(args, ensure_ascii=False),
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


class FigmaUiPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.project_root = self.work / "proj"
        self.project_root.mkdir(parents=True, exist_ok=True)
        (self.project_root / "project.godot").write_text('[application]\nconfig/name="tmp"\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_figma_baseline_and_compare_pipeline(self) -> None:
        figma_img = self.work / "figma.png"
        game_img = self.work / "game.png"
        scene_file = self.project_root / "scenes" / "main_scene_example.tscn"
        scene_file.parent.mkdir(parents=True, exist_ok=True)
        scene_file.write_text(
            "\n".join(
                [
                    '[gd_scene format=3]',
                    '[node name="Root" type="Node3D"]',
                    '[node name="PreviewImageA" type="TextureRect" parent="."]',
                    "offset_left = 0.0",
                    "offset_top = 0.0",
                    "offset_right = 80.0",
                    "offset_bottom = 100.0",
                    '[node name="PreviewImageB" type="TextureRect" parent="."]',
                    "offset_left = 100.0",
                    "offset_top = 0.0",
                    "offset_right = 220.0",
                    "offset_bottom = 100.0",
                ]
            ),
            encoding="utf-8",
        )
        figma_img.write_bytes(ONE_BY_ONE_PNG)
        game_img.write_bytes(ONE_BY_ONE_PNG)

        baseline = _run_tool(
            self.repo_root,
            "figma_design_to_baseline",
            {
                "project_root": str(self.project_root),
                "figma_file_key": "demo_file",
                "figma_node_id": "1:2",
                "figma_screenshot_file": str(figma_img),
                "figma_design_context": {
                    "frame": {"width": 1, "height": 1},
                    "styles": {"primaryColor": "#FFFFFF"},
                },
                "image_target_height": 120,
            },
        )
        self.assertTrue(Path(baseline["baseline_file"]).exists())

        compare = _run_tool(
            self.repo_root,
            "compare_figma_game_ui",
            {
                "project_root": str(self.project_root),
                "figma_baseline_file": baseline["baseline_file"],
                "game_snapshot_file": str(game_img),
            },
        )
        self.assertIn("overall_status", compare)
        self.assertIn("visual_diff", compare)
        compare_last = compare["exp_runtime"]["artifact_file"]

        annotate = _run_tool(
            self.repo_root,
            "annotate_ui_mismatch",
            {
                "project_root": str(self.project_root),
                "compare_report_file": compare_last,
            },
        )
        self.assertTrue(Path(annotate["annotation_file"]).exists())

        code, denied = _run_tool_raw(
            self.repo_root,
            "approve_ui_fix_plan",
            {
                "project_root": str(self.project_root),
                "compare_report_file": compare_last,
                "approved": True,
            },
        )
        self.assertEqual(code, 1)
        self.assertFalse(denied.get("ok", False))

        approval = _run_tool(
            self.repo_root,
            "approve_ui_fix_plan",
            {
                "project_root": str(self.project_root),
                "compare_report_file": compare_last,
                "approved": True,
                "approval_token": "approved-by-tester",
            },
        )
        self.assertTrue(Path(approval["approval_file"]).exists())

        suggestion = _run_tool(
            self.repo_root,
            "suggest_ui_fix_patch",
            {
                "project_root": str(self.project_root),
                "compare_report_file": compare_last,
                "approval_file": approval["approval_file"],
                "scene_file": str(scene_file),
            },
        )
        self.assertTrue(Path(suggestion["suggestion_file"]).exists())
        suggestion_payload = json.loads(Path(suggestion["suggestion_file"]).read_text(encoding="utf-8"))
        self.assertIn("uniform_scale_plan", suggestion_payload)


if __name__ == "__main__":
    unittest.main()
