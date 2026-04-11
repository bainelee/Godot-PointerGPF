import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from v2.mcp_core.flow_runner import FlowContractError, FlowRunOptions, FlowRunner, load_flow


class FlowRunnerContractTests(unittest.TestCase):
    def test_load_flow_rejects_unsupported_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow_file = Path(tmp) / "bad_flow.json"
            flow_file.write_text(
                json.dumps(
                    {
                        "flowId": "bad",
                        "steps": [{"id": "x", "action": "unsupported"}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(FlowContractError):
                load_flow(flow_file)

    def test_load_flow_accepts_interactive_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow_file = Path(tmp) / "interactive_flow.json"
            flow_file.write_text(
                json.dumps(
                    {
                        "flowId": "interactive",
                        "steps": [
                            {"id": "launch", "action": "launchGame"},
                            {"id": "click", "action": "click", "target": {"hint": "node_name:StartButton"}},
                            {"id": "wait", "action": "wait", "until": {"hint": "node_exists:GameLevel"}, "timeoutMs": 5000},
                            {"id": "check", "action": "check", "hint": "node_exists:GamePointerHud"},
                            {"id": "close", "action": "closeProject"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = load_flow(flow_file)

        self.assertEqual(payload["flowId"], "interactive")
        self.assertEqual(len(payload["steps"]), 5)
        self.assertEqual(payload["steps"][1]["action"], "click")
        self.assertEqual(payload["steps"][2]["action"], "wait")
        self.assertEqual(payload["steps"][3]["action"], "check")

    def test_load_flow_accepts_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow_file = Path(tmp) / "bom_flow.json"
            flow_file.write_text(
                json.dumps(
                    {
                        "flowId": "bom",
                        "steps": [{"id": "close", "action": "closeProject"}],
                    }
                ),
                encoding="utf-8-sig",
            )

            payload = load_flow(flow_file)

        self.assertEqual(payload["flowId"], "bom")

    def test_run_clears_stale_bridge_state_before_first_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            bridge_dir = project_root / "pointer_gpf" / "tmp"
            report_dir = project_root / "pointer_gpf" / "gpf-exp" / "runtime"
            bridge_dir.mkdir(parents=True, exist_ok=True)
            (bridge_dir / "command.json").write_text('{"stale": true}', encoding="utf-8")
            (bridge_dir / "response.json").write_text('{"stale": true}', encoding="utf-8")
            (bridge_dir / "runtime_diagnostics.json").write_text(
                '{"severity": "error", "items": [{"kind": "bridge_error", "message": "stale"}]}',
                encoding="utf-8",
            )

            runner = FlowRunner(
                FlowRunOptions(
                    project_root=project_root,
                    flow_file=project_root / "basicflow.json",
                    report_dir=report_dir,
                )
            )

            observed: dict[str, bool] = {}

            def fake_run_step(self: FlowRunner, step_index: int, step: dict[str, object]) -> dict[str, object]:
                observed["command_missing"] = not self.command_path().exists()
                observed["response_missing"] = not self.response_path().exists()
                observed["diagnostics_missing"] = not self.diagnostics_path().exists()
                return {"ok": True}

            with mock.patch.object(FlowRunner, "_run_step", autospec=True, side_effect=fake_run_step):
                report = runner.run({"flowId": "clean_start", "steps": [{"id": "launch", "action": "launchGame"}]})

        self.assertEqual(report["status"], "passed")
        self.assertTrue(observed["command_missing"])
        self.assertTrue(observed["response_missing"])
        self.assertTrue(observed["diagnostics_missing"])


if __name__ == "__main__":
    unittest.main()
