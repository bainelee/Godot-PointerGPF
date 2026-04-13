import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v2.mcp_core.windows_isolated_runtime import (
    IsolatedRuntimeSession,
    _wait_for_runtime_session,
    runtime_session_path,
    verify_isolated_runtime_stopped,
)


class _RunningProcess:
    def __init__(self, pid: int = 4321, poll_results: list[int | None] | None = None) -> None:
        self.pid = pid
        self._poll_results = list(poll_results or [None])

    def poll(self) -> int | None:
        if len(self._poll_results) > 1:
            return self._poll_results.pop(0)
        return self._poll_results[0]


class WindowsIsolatedRuntimeTests(unittest.TestCase):
    def test_wait_for_runtime_session_accepts_matching_session_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            session_path = runtime_session_path(project_root)
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(
                json.dumps(
                    {
                        "schema": "pointer_gpf.v2.runtime_session.v1",
                        "execution_mode": "isolated_runtime",
                        "process_id": 4321,
                        "desktop_name": "pointer_gpf_v2_test",
                    }
                ),
                encoding="utf-8",
            )
            session = IsolatedRuntimeSession(
                desktop_name="pointer_gpf_v2_test",
                desktop_handle=123,
                process=_RunningProcess(),
                project_root=project_root,
                host_desktop_name="Default",
            )

            payload = _wait_for_runtime_session(session, timeout_ms=200)

        self.assertEqual(payload["process_id"], 4321)
        self.assertEqual(payload["execution_mode"], "isolated_runtime")

    def test_verify_isolated_runtime_stopped_requires_stable_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = IsolatedRuntimeSession(
                desktop_name="pointer_gpf_v2_test",
                desktop_handle=123,
                process=_RunningProcess(poll_results=[None, 0, 0, 0]),
                project_root=Path(tmp),
                host_desktop_name="Default",
            )
            with patch(
                "v2.mcp_core.windows_isolated_runtime.time.monotonic",
                side_effect=[0.0, 0.0, 0.1, 0.35, 0.7, 0.9, 1.1],
            ), patch("v2.mcp_core.windows_isolated_runtime.time.sleep"):
                result = verify_isolated_runtime_stopped(session, timeout_ms=1000, stable_ms=200)

        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["separate_desktop"])
        self.assertGreaterEqual(result["stable_stop_ms"], 200)

    def test_verify_isolated_runtime_stopped_fails_when_process_keeps_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = IsolatedRuntimeSession(
                desktop_name="pointer_gpf_v2_test",
                desktop_handle=123,
                process=_RunningProcess(poll_results=[None, None, None]),
                project_root=Path(tmp),
                host_desktop_name="Default",
            )
            with patch(
                "v2.mcp_core.windows_isolated_runtime.time.monotonic",
                side_effect=[0.0, 0.0, 0.1, 0.3],
            ), patch("v2.mcp_core.windows_isolated_runtime.time.sleep"):
                result = verify_isolated_runtime_stopped(session, timeout_ms=150, stable_ms=100)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["separate_desktop"])
        self.assertEqual(result["stable_stop_ms"], 0)


if __name__ == "__main__":
    unittest.main()
