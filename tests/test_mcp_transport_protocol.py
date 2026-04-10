import json
import subprocess
import sys
import unittest
from pathlib import Path


class McpTransportProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.python_exe = sys.executable
        self.server = str(self.repo_root / "mcp" / "server.py")

    def test_json_line_initialize_roundtrip(self) -> None:
        proc = subprocess.Popen(
            [self.python_exe, self.server],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertIsNotNone(proc.stdin)
            self.assertIsNotNone(proc.stdout)
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
            }
            proc.stdin.write(json.dumps(init_req, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline().strip()
            payload = json.loads(line)
            self.assertEqual(payload["id"], 1)
            self.assertIn("result", payload)
            self.assertEqual(payload["result"]["protocolVersion"], "2024-11-05")
        finally:
            proc.kill()
            proc.wait(timeout=3)
            if proc.stdin:
                proc.stdin.close()
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()

    def test_content_length_initialize_roundtrip(self) -> None:
        proc = subprocess.Popen(
            [self.python_exe, self.server],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            self.assertIsNotNone(proc.stdin)
            self.assertIsNotNone(proc.stdout)
            init_req = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
            }
            body = json.dumps(init_req, ensure_ascii=False).encode("utf-8")
            msg = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
            proc.stdin.write(msg)
            proc.stdin.flush()

            header = proc.stdout.readline().decode("utf-8", errors="replace").strip()
            self.assertTrue(header.lower().startswith("content-length:"))
            blank = proc.stdout.readline()
            self.assertIn(blank, (b"\r\n", b"\n"))
            content_len = int(header.split(":", 1)[1].strip())
            payload_raw = proc.stdout.read(content_len)
            payload = json.loads(payload_raw.decode("utf-8"))
            self.assertEqual(payload["id"], 2)
            self.assertEqual(payload["result"]["protocolVersion"], "2024-11-05")
        finally:
            proc.kill()
            proc.wait(timeout=3)
            if proc.stdin:
                proc.stdin.close()
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()

    def test_stdio_exits_after_repeated_invalid_jsonl_frames(self) -> None:
        proc = subprocess.Popen(
            [self.python_exe, self.server],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIsNotNone(proc.stdin)
        try:
            proc.stdin.write(b"{not-valid-json}\n" * 8)
            proc.stdin.close()
            rc = proc.wait(timeout=15)
            self.assertEqual(rc, 2)
            err = proc.stderr.read().decode("utf-8", errors="replace")
            self.assertIn("too many consecutive", err.lower())
            proc.stdout.close()
            proc.stderr.close()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
