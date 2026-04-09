#!/usr/bin/env python3
"""Scenario registry for game test runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ScenarioDef:
    name: str
    system: str
    scene: str
    profiles: tuple[str, ...]
    supported_modes: tuple[str, ...]
    preconditions: tuple[str, ...] = ()
    default_args: tuple[str, ...] = ()
    user_args: tuple[str, ...] = ()
    screenshot_prefix: str = ""


_SCENARIOS: tuple[ScenarioDef, ...] = (
    ScenarioDef(
        name="exploration_smoke",
        system="exploration",
        scene="res://scenes/test/exploration_smoke_test.tscn",
        profiles=("smoke",),
        supported_modes=("vm", "local", "headless"),
        default_args=("--quit-after", "400"),
    ),
    ScenarioDef(
        name="debug_frame_print_smoke",
        system="debug",
        scene="res://scenes/test/debug_frame_print_test.tscn",
        profiles=("smoke",),
        supported_modes=("vm", "local", "headless"),
        default_args=("--quit-after", "400"),
    ),
    ScenarioDef(
        name="exploration_gameplay_flow_test",
        system="exploration",
        scene="res://scenes/test/exploration_gameplay_flow_test.tscn",
        profiles=("smoke", "flow"),
        supported_modes=("vm", "local", "headless"),
        default_args=("--quit-after", "600"),
        screenshot_prefix="flow_exploration_",
    ),
    ScenarioDef(
        name="visual_regression_probe",
        system="visual",
        scene="res://scenes/test/visual_regression_probe_test.tscn",
        profiles=("smoke",),
        supported_modes=("vm", "local", "headless"),
        default_args=("--quit-after", "400"),
        user_args=("--assert-baseline",),
        screenshot_prefix="visual_ui_button_",
    ),
)


def list_scenarios() -> list[dict]:
    return [
        {
            "name": s.name,
            "system": s.system,
            "profiles": list(s.profiles),
            "supported_modes": list(s.supported_modes),
            "preconditions": list(s.preconditions),
            "scene": s.scene,
            "user_args": list(s.user_args),
            "screenshot_prefix": s.screenshot_prefix,
        }
        for s in _SCENARIOS
    ]


def get_scenario_by_name(name: str) -> Optional[ScenarioDef]:
    for s in _SCENARIOS:
        if s.name == name:
            return s
    return None


def get_default_scenario_by_system(system: str) -> Optional[ScenarioDef]:
    for s in _SCENARIOS:
        if s.system == system:
            return s
    return None
