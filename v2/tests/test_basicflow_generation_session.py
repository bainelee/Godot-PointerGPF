import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.basicflow_generation_session import (
    BasicFlowGenerationSessionError,
    answer_basicflow_generation_session,
    complete_basicflow_generation_session,
    start_basicflow_generation_session,
)


class BasicFlowGenerationSessionTests(unittest.TestCase):
    def test_session_flow_can_collect_answers_and_generate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text(
                '[application]\nrun/main_scene="res://scenes/main.tscn"\n',
                encoding="utf-8",
            )
            (project_root / "scenes").mkdir(parents=True, exist_ok=True)
            (project_root / "scenes" / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")

            session = start_basicflow_generation_session(project_root)
            session_id = session["session_id"]
            after_q1 = answer_basicflow_generation_session(
                project_root,
                session_id=session_id,
                question_id="main_scene_is_entry",
                answer="true",
            )
            after_q2 = answer_basicflow_generation_session(
                project_root,
                session_id=session_id,
                question_id="tested_features",
                answer="进入主流程,基础操作",
            )
            after_q3 = answer_basicflow_generation_session(
                project_root,
                session_id=session_id,
                question_id="include_screenshot_evidence",
                answer="false",
            )
            result = complete_basicflow_generation_session(project_root, session_id=session_id)

        self.assertEqual(after_q1["next_question"]["id"], "tested_features")
        self.assertEqual(after_q2["next_question"]["id"], "include_screenshot_evidence")
        self.assertIsNone(after_q3["next_question"])
        self.assertEqual(result["status"], "generated")

    def test_session_requires_followup_entry_scene_when_main_scene_is_not_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "project.godot").write_text("[application]\n", encoding="utf-8")

            session = start_basicflow_generation_session(project_root)
            session_id = session["session_id"]
            after_q1 = answer_basicflow_generation_session(
                project_root,
                session_id=session_id,
                question_id="main_scene_is_entry",
                answer="false",
            )

        self.assertEqual(after_q1["next_question"]["id"], "entry_scene_path")

    def test_complete_generation_session_rejects_incomplete_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            session = start_basicflow_generation_session(project_root)

            with self.assertRaises(BasicFlowGenerationSessionError):
                complete_basicflow_generation_session(project_root, session_id=session["session_id"])


if __name__ == "__main__":
    unittest.main()
