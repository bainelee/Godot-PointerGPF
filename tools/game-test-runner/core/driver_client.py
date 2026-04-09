#!/usr/bin/env python3
"""File-based client for TestDriver autoload."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DriverPaths:
    cmd_file: Path
    resp_file: Path


class DriverClient:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.paths = DriverPaths(
            cmd_file=base_dir / "command.json",
            resp_file=base_dir / "response.json",
        )
        self._seq = 0
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._seq = self._detect_existing_seq()

    def _detect_existing_seq(self) -> int:
        seq = 0
        for p in (self.paths.cmd_file, self.paths.resp_file):
            if not p.exists():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            try:
                seq = max(seq, int(data.get("seq", 0)))
            except (TypeError, ValueError):
                continue
        return seq

    def send_command(self, action: str, params: dict[str, Any] | None = None) -> int:
        self._seq += 1
        if self.paths.resp_file.exists():
            self.paths.resp_file.unlink(missing_ok=True)
        payload = {
            "seq": self._seq,
            "action": action,
            "params": params or {},
            "sent_at_ms": int(time.time() * 1000),
        }
        self.paths.cmd_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return self._seq

    def wait_response(self, seq: int, timeout_sec: float = 10.0, poll_interval_sec: float = 0.05) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() <= deadline:
            if self.paths.resp_file.exists():
                try:
                    data = json.loads(self.paths.resp_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    time.sleep(poll_interval_sec)
                    continue
                if int(data.get("seq", -1)) == seq:
                    return data
            time.sleep(poll_interval_sec)
        raise TimeoutError(f"timeout waiting response seq={seq}")

    def send_and_wait(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        timeout_sec: float = 10.0,
        poll_interval_sec: float = 0.05,
    ) -> dict[str, Any]:
        seq = self.send_command(action=action, params=params)
        return self.wait_response(seq=seq, timeout_sec=timeout_sec, poll_interval_sec=poll_interval_sec)
