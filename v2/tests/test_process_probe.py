from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2.mcp_core.process_probe import (
    detect_multiple_project_processes,
    is_editor_process_running,
    is_pid_running,
    list_project_processes,
)


class ProcessProbeTests(unittest.TestCase):
    def test_list_project_processes_uses_unescaped_project_path_in_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            calls: list[list[str]] = []

            def fake_run(args: list[str], **_: object):
                calls.append(args)
                return type(
                    "Completed",
                    (),
                    {
                        "stdout": json.dumps(
                            {"ProcessId": 1234, "Name": "Godot.exe", "CommandLine": f"Godot -e --path {project_root.resolve()}"}
                        )
                    },
                )()

            result = list_project_processes(project_root, subprocess_run=fake_run)

        self.assertEqual(len(result), 1)
        probe = calls[0][2]
        self.assertIn(str(project_root.resolve()), probe)
        self.assertNotIn("\\\\", probe)

    def test_is_editor_process_running_ignores_runtime_process(self) -> None:
        project_root = Path.cwd()
        result = is_editor_process_running(
            project_root,
            list_project_editor_processes=lambda _: [],
        )
        self.assertFalse(result)

    def test_is_pid_running_returns_true_when_process_exists(self) -> None:
        fake_run = lambda *args, **kwargs: type("Completed", (), {"stdout": "1234\n"})()
        self.assertTrue(is_pid_running(1234, subprocess_run=fake_run))

    def test_detect_multiple_project_processes_reports_extra_editors(self) -> None:
        project_root = Path.cwd()
        result = detect_multiple_project_processes(
            project_root,
            list_project_editor_processes=lambda _: [
                {"ProcessId": 1, "Name": "Godot.exe", "CommandLine": "godot -e --path a"},
                {"ProcessId": 2, "Name": "Godot.exe", "CommandLine": "godot -e --path a"},
            ],
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["project_process_count"], 2)


if __name__ == "__main__":
    unittest.main()
