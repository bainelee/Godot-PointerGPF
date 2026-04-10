"""Structured trace for verify / locate / patch / retest (R-001 evidence)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PhaseKind = Literal["verify", "locate", "patch", "retest", "bootstrap"]


@dataclass
class RemediationTrace:
    run_id: str
    events: list[dict[str, Any]] = field(default_factory=list)

    def append(self, kind: PhaseKind, payload: dict[str, Any]) -> None:
        self.events.append({"kind": kind, "payload": dict(payload)})

    def to_json(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "events": list(self.events)}
