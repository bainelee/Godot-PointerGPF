"""FlowRunner parallel observation of pointer_gpf/tmp/runtime_diagnostics.json."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))


class TestFlowEngineDiagnostics(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        (self.root / "pointer_gpf" / "tmp").mkdir(parents=True)
        (self.root / "project.godot").write_text('[application]\nconfig/name="t"\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.td.cleanup()

    def test_engine_stalled_when_diagnostics_error_while_waiting_bridge(self) -> None:
        from flow_execution import FlowExecutionEngineStalled, FlowRunOptions, FlowRunner

        flow_dir = self.root / "pointer_gpf" / "generated_flows"
        flow_dir.mkdir(parents=True)
        flow_file = flow_dir / "diag_flow.json"
        flow_payload = {"flowId": "diag_flow", "steps": [{"id": "s1", "action": "click", "target": {"hint": "none"}}]}
        flow_file.write_text(json.dumps(flow_payload), encoding="utf-8")
        diag_path = self.root / "pointer_gpf" / "tmp" / "runtime_diagnostics.json"

        def inject() -> None:
            time.sleep(0.06)
            diag_path.write_text(
                json.dumps(
                    {
                        "schema": "pointer_gpf.runtime_diagnostics.v1",
                        "severity": "error",
                        "summary": "script failed",
                        "items": [{"kind": "push_error", "message": "boom", "file": "", "line": 0}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        threading.Thread(target=inject, daemon=True).start()
        report_dir = self.root / "pointer_gpf" / "gpf-exp" / "runtime"
        report_dir.mkdir(parents=True)
        opts = FlowRunOptions(
            project_root=self.root,
            flow_file=flow_file,
            report_dir=report_dir,
            step_timeout_ms=5000,
            shell_report=False,
            observe_engine_errors=True,
        )
        runner = FlowRunner(opts)
        with self.assertRaises(FlowExecutionEngineStalled):
            runner.run(flow_payload)

    def test_observe_engine_errors_false_does_not_read_diagnostics(self) -> None:
        from flow_execution import FlowExecutionTimeout, FlowRunOptions, FlowRunner

        flow_dir = self.root / "pointer_gpf" / "generated_flows"
        flow_dir.mkdir(parents=True)
        flow_file = flow_dir / "diag_flow2.json"
        flow_payload = {"flowId": "diag_flow2", "steps": [{"id": "s1", "action": "click", "target": {"hint": "none"}}]}
        flow_file.write_text(json.dumps(flow_payload), encoding="utf-8")
        diag_path = self.root / "pointer_gpf" / "tmp" / "runtime_diagnostics.json"
        diag_path.write_text(
            json.dumps({"schema": "pointer_gpf.runtime_diagnostics.v1", "severity": "error", "summary": "x", "items": []}),
            encoding="utf-8",
        )
        report_dir = self.root / "pointer_gpf" / "gpf-exp" / "runtime"
        report_dir.mkdir(parents=True)
        opts = FlowRunOptions(
            project_root=self.root,
            flow_file=flow_file,
            report_dir=report_dir,
            step_timeout_ms=400,
            shell_report=False,
            observe_engine_errors=False,
        )
        runner = FlowRunner(opts)
        with self.assertRaises(FlowExecutionTimeout):
            runner.run(flow_payload)


if __name__ == "__main__":
    unittest.main()
