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

    def test_load_flow_accepts_delay_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow_file = Path(tmp) / "delay_flow.json"
            flow_file.write_text(
                json.dumps(
                    {
                        "flowId": "delay_flow",
                        "steps": [
                            {"id": "launch", "action": "launchGame"},
                            {"id": "pause", "action": "delay", "timeoutMs": 5000},
                            {"id": "close", "action": "closeProject"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = load_flow(flow_file)

        self.assertEqual(payload["steps"][1]["action"], "delay")
        self.assertEqual(payload["steps"][1]["timeoutMs"], 5000)

    def test_load_flow_accepts_capture_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow_file = Path(tmp) / "capture_flow.json"
            flow_file.write_text(
                json.dumps(
                    {
                        "flowId": "capture_flow",
                        "steps": [
                            {"id": "launch", "action": "launchGame"},
                            {
                                "id": "capture_yaw",
                                "action": "capture",
                                "captureKey": "player_yaw",
                                "metric": "rotation_y",
                                "target": {"hint": "node_name:FPSController"},
                            },
                            {"id": "close", "action": "closeProject"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = load_flow(flow_file)

        self.assertEqual(payload["steps"][1]["action"], "capture")
        self.assertEqual(payload["steps"][1]["captureKey"], "player_yaw")

    def test_load_flow_accepts_generic_evidence_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow_file = Path(tmp) / "runtime_evidence_flow.json"
            flow_file.write_text(
                json.dumps(
                    {
                        "flowId": "runtime_evidence_flow",
                        "steps": [
                            {"id": "launch", "action": "launchGame"},
                            {
                                "id": "sample_value",
                                "action": "sample",
                                "target": {"hint": "node_name:Enemy"},
                                "metric": {"kind": "node_property", "property_path": "modulate"},
                                "windowMs": 250,
                                "intervalMs": 50,
                                "evidenceKey": "enemy_modulate_window",
                            },
                            {
                                "id": "observe_signal",
                                "action": "observe",
                                "target": {"hint": "node_name:Enemy"},
                                "event": {"kind": "signal_emitted", "signal_name": "hit_taken"},
                                "windowMs": 250,
                                "evidenceKey": "enemy_hit_signal_window",
                            },
                            {"id": "close", "action": "closeProject"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = load_flow(flow_file)

        self.assertEqual(payload["steps"][1]["action"], "sample")
        self.assertEqual(payload["steps"][2]["action"], "observe")

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

    def test_run_collects_runtime_evidence_from_step_responses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            report_dir = project_root / "pointer_gpf" / "gpf-exp" / "runtime"
            runner = FlowRunner(
                FlowRunOptions(
                    project_root=project_root,
                    flow_file=project_root / "basicflow.json",
                    report_dir=report_dir,
                )
            )

            def fake_run_step(self: FlowRunner, step_index: int, step: dict[str, object]) -> dict[str, object]:
                response = {
                    "ok": True,
                    "runtime_evidence_refs": ["enemy_modulate_window"],
                    "runtime_evidence_records": [
                        {
                            "evidence_id": "enemy_modulate_window",
                            "record_type": "sample_result",
                            "status": "passed",
                            "samples": [],
                        }
                    ],
                }
                self._record_runtime_evidence_from_response(response)
                return response

            with mock.patch.object(FlowRunner, "_run_step", autospec=True, side_effect=fake_run_step):
                report = runner.run({"flowId": "evidence", "steps": [{"id": "sample", "action": "sample"}]})

        self.assertEqual(report["runtime_evidence_refs"], ["enemy_modulate_window"])
        self.assertEqual(report["runtime_evidence_summary"]["record_count"], 1)
        self.assertEqual(report["runtime_evidence_records"][0]["record_type"], "sample_result")

    def test_run_deduplicates_runtime_evidence_records_by_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            report_dir = project_root / "pointer_gpf" / "gpf-exp" / "runtime"
            runner = FlowRunner(
                FlowRunOptions(
                    project_root=project_root,
                    flow_file=project_root / "basicflow.json",
                    report_dir=report_dir,
                )
            )

            def fake_run_step(self: FlowRunner, step_index: int, step: dict[str, object]) -> dict[str, object]:
                response = {
                    "ok": True,
                    "runtime_evidence_refs": ["same_evidence"],
                    "runtime_evidence_records": [
                        {
                            "evidence_id": "same_evidence",
                            "record_type": "sample_result",
                            "status": "passed",
                        }
                    ],
                }
                self._record_runtime_evidence_from_response(response)
                return response

            with mock.patch.object(FlowRunner, "_run_step", autospec=True, side_effect=fake_run_step):
                report = runner.run(
                    {
                        "flowId": "evidence",
                        "steps": [
                            {"id": "sample", "action": "sample"},
                            {"id": "check", "action": "check"},
                        ],
                    }
                )

        self.assertEqual(report["runtime_evidence_refs"], ["same_evidence"])
        self.assertEqual(report["runtime_evidence_summary"]["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
