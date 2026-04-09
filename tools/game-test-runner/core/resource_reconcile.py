#!/usr/bin/env python3
"""Basic data test: dual-track resource reconcile flow."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESOURCE_KEYS = [
    "cognition",
    "computation",
    "willpower",
    "permission",
    "info",
    "truth",
    "staff",
    "labor",
    "eroded",
    "investigator",
]


def _utc_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _parse_iso(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _flatten(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            _flatten(key, v, out)
        return
    out[prefix] = value


def _flat_dict(value: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    _flatten("", value, out)
    return out


def _diff_values(a: dict[str, Any], b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    af = _flat_dict(a)
    bf = _flat_dict(b)
    keys = sorted(set(af.keys()) | set(bf.keys()))
    out: dict[str, dict[str, Any]] = {}
    for key in keys:
        va = af.get(key)
        vb = bf.get(key)
        if va == vb:
            continue
        delta: float | None = None
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            delta = float(vb) - float(va)
        out[key] = {"from": va, "to": vb, "delta": delta}
    return out


def _canonical_resources(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    # Runtime getState(resources) is flat; save file is nested.
    if any(k in raw for k in ("factors", "currency", "personnel")):
        factors = raw.get("factors", {}) if isinstance(raw.get("factors", {}), dict) else {}
        currency = raw.get("currency", {}) if isinstance(raw.get("currency", {}), dict) else {}
        personnel = raw.get("personnel", {}) if isinstance(raw.get("personnel", {}), dict) else {}
        return {
            "cognition": factors.get("cognition"),
            "computation": factors.get("computation"),
            "willpower": factors.get("willpower"),
            "permission": factors.get("permission"),
            "info": currency.get("info"),
            "truth": currency.get("truth"),
            "staff": personnel.get("staff"),
            "labor": personnel.get("labor"),
            "eroded": personnel.get("eroded"),
            "investigator": personnel.get("investigator"),
        }
    return {
        "cognition": raw.get("cognition"),
        "computation": raw.get("computation"),
        "willpower": raw.get("willpower"),
        "permission": raw.get("permission"),
        "info": raw.get("info"),
        "truth": raw.get("truth"),
        "staff": raw.get("staff"),
        "labor": raw.get("labor", 0),
        "eroded": raw.get("eroded", 0),
        "investigator": raw.get("investigator", 0),
    }


def _read_events(run_root: Path) -> list[dict[str, Any]]:
    events_path = run_root / "logs" / "driver_flow_events.jsonl"
    if not events_path.exists():
        return []
    lines = events_path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _snapshot_event_ts(events: list[dict[str, Any]], step_id: str) -> str:
    for event in events:
        if str(event.get("type", "")) != "step_completed":
            continue
        if str(event.get("step_id", "")) == step_id:
            return str(event.get("ts", ""))
    return ""


def _extract_snapshot(run_root: Path, step_id: str) -> dict[str, Any]:
    driver_flow = _read_json(run_root / "logs" / "driver_flow.json", {})
    steps = driver_flow.get("steps", []) if isinstance(driver_flow, dict) else []
    snapshot_data: dict[str, Any] = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("step_id", "")) != step_id:
            continue
        response = step.get("response", {})
        if isinstance(response, dict):
            data = response.get("data", {})
            if isinstance(data, dict):
                snapshot_data = data
        break
    resources_raw = snapshot_data.get("resources", {}) if isinstance(snapshot_data.get("resources", {}), dict) else {}
    game_total_hours = snapshot_data.get("game_total_hours", None)
    if isinstance(game_total_hours, (int, float)):
        game_total_hours = float(game_total_hours)
    else:
        game_total_hours = None
    events = _read_events(run_root)
    return {
        "step_id": step_id,
        "resources": _canonical_resources(resources_raw),
        "game_total_hours": game_total_hours,
        "event_utc": _snapshot_event_ts(events, step_id),
    }


def _run_flow_stepwise_shared(
    *,
    project_root: Path,
    flow_file: Path,
    godot_bin: str,
    user_data_dir: Path,
    timeout_sec: int,
    run_id: str,
) -> dict[str, Any]:
    """Run flow via Cursor chat/stepwise path with the same three-phase contract."""
    script = project_root / "tools" / "game-test-runner" / "scripts" / "run_gameplay_stepwise_chat.py"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(script),
        "--project-root",
        str(project_root),
        "--godot-bin",
        godot_bin,
        "--flow-file",
        str(flow_file),
        "--timeout-sec",
        str(int(timeout_sec)),
        "--user-data-dir",
        str(user_data_dir),
    ]
    rid = str(run_id or "").strip()
    if rid:
        cmd.extend(["--run-id", rid])
    proc = subprocess.run(
        cmd,
        cwd=str(project_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout = proc.stdout or ""
    summary_path = ""
    for line in stdout.splitlines():
        if line.startswith("SUMMARY_JSON="):
            summary_path = line.split("=", 1)[-1].strip()
            break
    flow_payload: dict[str, Any] = {}
    if summary_path:
        sp = Path(summary_path)
        if sp.exists():
            try:
                loaded = json.loads(sp.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    flow_payload = loaded
            except json.JSONDecodeError:
                flow_payload = {}
    phases = flow_payload.get("phases") if isinstance(flow_payload.get("phases"), list) else []
    phase0 = phases[0] if phases and isinstance(phases[0], dict) else {}
    phase_root = str(phase0.get("artifact_root", "")).strip()
    st = str(phase0.get("status", "")).strip()
    passed = st == "passed" and int(proc.returncode) == 0 and bool(phase_root)
    flow_id = flow_file.stem
    try:
        raw_flow = json.loads(flow_file.read_text(encoding="utf-8"))
        if isinstance(raw_flow, dict) and raw_flow.get("flowId"):
            flow_id = str(raw_flow.get("flowId"))
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "flow_id": flow_id,
        "run_id": str(phase0.get("run_id", "") or "").strip() or rid,
        "run_root": phase_root,
        "status": "passed" if passed else "failed",
        "stepwise_exit_code": int(proc.returncode),
        "stepwise_summary_json": summary_path,
        "stepwise_stdout_tail": stdout[-6000:],
        "stepwise_stderr_tail": (proc.stderr or "")[-3000:],
    }


def _load_saved_resources(user_data_dir: Path, slot: int = 0) -> dict[str, Any]:
    save_path = user_data_dir / "saves" / f"slot_{slot}.json"
    payload = _read_json(save_path, {})
    if isinstance(payload, dict) and ("resources" in payload) and isinstance(payload.get("resources"), dict):
        return _canonical_resources(payload.get("resources", {}))
    appdata = Path(str(Path.home()))
    appdata_env = str(os.environ.get("APPDATA", "")).strip()
    if appdata_env:
        appdata = Path(appdata_env)
    fallback = appdata / "Godot" / "app_userdata" / "GodotGame" / "saves" / f"slot_{slot}.json"
    payload_fallback = _read_json(fallback, {})
    if (
        isinstance(payload_fallback, dict)
        and ("resources" in payload_fallback)
        and isinstance(payload_fallback.get("resources"), dict)
    ):
        return _canonical_resources(payload_fallback.get("resources", {}))
    return {}


def _time_window(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    tg_a = a.get("game_total_hours")
    tg_b = b.get("game_total_hours")
    tg_delta = None
    if isinstance(tg_a, (int, float)) and isinstance(tg_b, (int, float)):
        tg_delta = float(tg_b) - float(tg_a)
    tw_a = _parse_iso(str(a.get("event_utc", "")))
    tw_b = _parse_iso(str(b.get("event_utc", "")))
    tw_delta_sec = None
    if tw_a and tw_b:
        tw_delta_sec = (tw_b - tw_a).total_seconds()
    return {
        "from": str(a.get("step_id", "")),
        "to": str(b.get("step_id", "")),
        "game_hours_delta": tg_delta,
        "wall_seconds_delta": tw_delta_sec,
    }


def _resource_delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    keys = sorted(set(a.keys()) | set(b.keys()))
    for key in keys:
        va = a.get(key)
        vb = b.get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            out[key] = float(vb) - float(va)
    return out


def _resource_delta_only_numeric(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in RESOURCE_KEYS:
        va = a.get(key)
        vb = b.get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            out[key] = float(vb) - float(va)
    return out


def _resource_subtract(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in RESOURCE_KEYS:
        va = a.get(key)
        vb = b.get(key, 0.0)
        if isinstance(va, (int, float)):
            vb_num = float(vb) if isinstance(vb, (int, float)) else 0.0
            out[key] = float(va) - vb_num
    return out


def _resource_sum(resources: dict[str, Any]) -> float:
    total = 0.0
    for key in RESOURCE_KEYS:
        value = resources.get(key)
        if isinstance(value, (int, float)):
            total += float(value)
    return total


def _gate_error_code(gate_name: str) -> str:
    mapping = {
        "phase1_passed": "E_PHASE1_FLOW_FAILED",
        "phase2_passed": "E_PHASE2_FLOW_FAILED",
        "save_resources_loaded": "E_SAVE_RESOURCE_MISSING",
    }
    return str(mapping.get(str(gate_name), "E_UNKNOWN_GATE"))


def _load_basic_model(project_root: Path, target_id: str, start_snapshot: dict[str, Any]) -> dict[str, Any]:
    target_info = _read_json(project_root / "datas" / "target_info.json", {})
    target_size_cfg = _read_json(project_root / "datas" / "target_size_config.json", {})
    cleanup_cfg = _read_json(project_root / "datas" / "cleanup_system.json", {})
    construction_cfg = _read_json(project_root / "datas" / "construction_system.json", {})
    staff_cfg = _read_json(project_root / "datas" / "staff_system.json", {})
    game_values_cfg = _read_json(project_root / "datas" / "game_values.json", {})

    size_id = ""
    if isinstance(target_info, dict):
        rooms = target_info.get("rooms", [])
        if isinstance(rooms, list):
            for room in rooms:
                if not isinstance(room, dict):
                    continue
                if str(room.get("id", "")) == target_id:
                    size_id = str(room.get("3d_size", "")).strip()
                    break
    units = 1
    sizes = target_size_cfg.get("sizes", {}) if isinstance(target_size_cfg, dict) else {}
    if isinstance(sizes, dict):
        size = sizes.get(size_id, {})
        if isinstance(size, dict):
            units = max(1, int(size.get("units", 1)))

    cleanup_match: dict[str, Any] = {}
    cleanup_arr = cleanup_cfg.get("cleanup", []) if isinstance(cleanup_cfg, dict) else []
    if isinstance(cleanup_arr, list):
        for item in cleanup_arr:
            if not isinstance(item, dict):
                continue
            umin = int(item.get("units_min", item.get("units", -999)))
            umax = int(item.get("units_max", item.get("units", 999)))
            if units >= umin and units <= umax:
                cleanup_match = item
                break
    construction_map = construction_cfg.get("construction", {}) if isinstance(construction_cfg, dict) else {}
    construction_zone1 = construction_map.get("1", {}) if isinstance(construction_map, dict) else {}
    build_hours = float(units * float(construction_zone1.get("hours_per_unit", 2.0) if isinstance(construction_zone1, dict) else 2.0))

    start_resources = start_snapshot.get("resources", {}) if isinstance(start_snapshot, dict) else {}
    staff_count = int(start_resources.get("staff", 0)) if isinstance(start_resources, dict) else 0
    eroded_count = int(start_resources.get("eroded", 0)) if isinstance(start_resources, dict) else 0
    active_staffs = max(0, staff_count - eroded_count)
    cognition_per_staff_per_hour = int(
        (staff_cfg.get("cognition", {}) if isinstance(staff_cfg, dict) else {}).get(
            "consumption_per_staff_per_hour", 1
        )
    )
    cognition_rate = -float(active_staffs * cognition_per_staff_per_hour)

    # Compatibility path: read production rate from project data.
    permission_per_unit_per_hour = int(
        (game_values_cfg.get("research_output", {}) if isinstance(game_values_cfg, dict) else {})
        .get("3", {})
        .get("per_unit_per_hour", 10)
    )
    permission_rate = float(units * permission_per_unit_per_hour)

    return {
        "units": units,
        "active_staffs": active_staffs,
        "rates_per_hour": {
            "cognition": cognition_rate,
            "permission_research_zone": permission_rate,
            "willpower_zone_fixed": -1.0,
        },
        "build_hours": build_hours,
        "one_off": {
            "cleanup": {"info": -float(int(cleanup_match.get("info", 0)))},
            "build": {
                "info": -float(int(construction_zone1.get("info", 0))),
                "permission": -float(int(construction_zone1.get("permission", 0))),
            },
        },
    }


def _window_expected(
    *,
    observed_hours: float,
    settled_hours: float,
    one_off: dict[str, float],
    rates: dict[str, float],
    rate_activation_hours: dict[str, float] | None = None,
) -> dict[str, dict[str, float]]:
    activation = rate_activation_hours if isinstance(rate_activation_hours, dict) else {}
    resources = sorted(set(one_off.keys()) | set(rates.keys()))
    out: dict[str, dict[str, float]] = {}
    for key in resources:
        one = float(one_off.get(key, 0.0))
        rate = float(rates.get(key, 0.0))
        start_after = float(activation.get(key, 0.0))
        observed_active = max(0.0, observed_hours - start_after)
        settled_active = max(0.0, settled_hours - start_after)
        expected_cont = one + (rate * observed_active)
        expected_disc = one + (rate * settled_active)
        delay_window = rate * (settled_active - observed_active)
        out[key] = {
            "one_off": one,
            "rate_per_hour": rate,
            "rate_activation_after_hours": start_after,
            "expected_continuous": expected_cont,
            "expected_discrete": expected_disc,
            "delay_window": delay_window,
            "discrete_rounding": expected_disc - expected_cont - delay_window,
        }
    return out


def _attribution_for_window(
    *,
    name: str,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    one_off: dict[str, float],
    rates: dict[str, float],
    rate_activation_hours: dict[str, float] | None = None,
) -> dict[str, Any]:
    before_res = before_snapshot.get("resources", {}) if isinstance(before_snapshot, dict) else {}
    after_res = after_snapshot.get("resources", {}) if isinstance(after_snapshot, dict) else {}
    actual_delta = _resource_delta(before_res if isinstance(before_res, dict) else {}, after_res if isinstance(after_res, dict) else {})

    before_tg = before_snapshot.get("game_total_hours")
    after_tg = after_snapshot.get("game_total_hours")
    observed_hours = 0.0
    settled_hours = 0.0
    if isinstance(before_tg, (int, float)) and isinstance(after_tg, (int, float)):
        observed_hours = float(after_tg) - float(before_tg)
        settled_hours = float(math.floor(after_tg) - math.floor(before_tg))
    expected = _window_expected(
        observed_hours=observed_hours,
        settled_hours=settled_hours,
        one_off=one_off,
        rates=rates,
        rate_activation_hours=rate_activation_hours,
    )
    resources = sorted(set(actual_delta.keys()) | set(expected.keys()))
    per_resource: dict[str, dict[str, float]] = {}
    for key in resources:
        actual = float(actual_delta.get(key, 0.0))
        e = expected.get(
            key,
            {
                "one_off": 0.0,
                "rate_per_hour": 0.0,
                "expected_continuous": 0.0,
                "expected_discrete": 0.0,
                "delay_window": 0.0,
                "discrete_rounding": 0.0,
            },
        )
        true_mismatch = actual - float(e.get("expected_discrete", 0.0))
        per_resource[key] = {
            "actual_delta": actual,
            "one_off": float(e.get("one_off", 0.0)),
            "rate_per_hour": float(e.get("rate_per_hour", 0.0)),
            "rate_activation_after_hours": float(e.get("rate_activation_after_hours", 0.0)),
            "expected_continuous": float(e.get("expected_continuous", 0.0)),
            "expected_discrete": float(e.get("expected_discrete", 0.0)),
            "delay_window": float(e.get("delay_window", 0.0)),
            "discrete_rounding": float(e.get("discrete_rounding", 0.0)),
            "true_mismatch": true_mismatch,
        }
    ignored_raw = settled_hours - observed_hours
    return {
        "name": name,
        "observed_game_hours": observed_hours,
        "settled_game_hours": settled_hours,
        "ignored_runtime_hours_raw": ignored_raw,
        "ignored_runtime_hours": max(0.0, ignored_raw),
        "per_resource": per_resource,
    }


def run_basic_data_validation(
    *,
    project_root: Path,
    godot_bin: str,
    timeout_sec: int,
    output_json: Path,
) -> tuple[dict[str, Any], int]:
    phase1_flow = project_root / "flows" / "suites" / "regression" / "gameplay" / "basic_data_slot0_phase1.json"
    phase2_flow = project_root / "flows" / "suites" / "regression" / "gameplay" / "basic_data_slot0_phase2.json"
    if not phase1_flow.exists():
        raise FileNotFoundError(f"phase1 flow not found: {phase1_flow}")
    if not phase2_flow.exists():
        raise FileNotFoundError(f"phase2 flow not found: {phase2_flow}")

    test_id = f"basic_data_test_{_utc_id()}"
    shared_user_data_dir = project_root / "artifacts" / "test-runs" / test_id / "shared_user_data"
    shared_user_data_dir.mkdir(parents=True, exist_ok=True)

    phase1 = _run_flow_stepwise_shared(
        project_root=project_root,
        flow_file=phase1_flow,
        godot_bin=godot_bin,
        user_data_dir=shared_user_data_dir,
        timeout_sec=timeout_sec,
        run_id=f"{test_id}_phase1",
    )
    phase2 = _run_flow_stepwise_shared(
        project_root=project_root,
        flow_file=phase2_flow,
        godot_bin=godot_bin,
        user_data_dir=shared_user_data_dir,
        timeout_sec=timeout_sec,
        run_id=f"{test_id}_phase2",
    )

    phase1_root = Path(phase1["run_root"])
    phase2_root = Path(phase2["run_root"])
    r0 = _extract_snapshot(phase1_root, "snapshot_r0")
    target_a_cleaned = _extract_snapshot(phase1_root, "snapshot_target_a_cleaned")
    target_a_built = _extract_snapshot(phase1_root, "snapshot_target_a_built")
    target_b_cleaned = _extract_snapshot(phase1_root, "snapshot_target_b_cleaned")
    target_b_built = _extract_snapshot(phase1_root, "snapshot_target_b_built")
    r2 = _extract_snapshot(phase1_root, "snapshot_r2")
    r2_saved = _extract_snapshot(phase1_root, "snapshot_r2_saved")
    rs = {"step_id": "save_slot_0", "resources": _load_saved_resources(shared_user_data_dir, slot=0)}
    r3 = _extract_snapshot(phase2_root, "snapshot_r3")

    diff_r2_saved_rs = _diff_values(r2_saved.get("resources", {}), rs.get("resources", {}))
    diff_rs_r3 = _diff_values(rs.get("resources", {}), r3.get("resources", {}))
    diff_r2_saved_r3 = _diff_values(r2_saved.get("resources", {}), r3.get("resources", {}))
    diff_r2_r2_saved = _diff_values(r2.get("resources", {}), r2_saved.get("resources", {}))

    stage_cleanup_a = _time_window(r0, target_a_cleaned)
    stage_build_a = _time_window(target_a_cleaned, target_a_built)
    stage_cleanup_b = _time_window(target_a_built, target_b_cleaned)
    stage_build_b = _time_window(target_b_cleaned, target_b_built)
    stage_total = _time_window(r0, r2)
    stage_reopen = _time_window(r2, r3)

    save_window_attr = _attribution_for_window(
        name="save_window",
        before_snapshot=r2,
        after_snapshot=r2_saved,
        one_off={},
        rates={},
    )
    reopen_attr = _attribution_for_window(
        name="reopen",
        before_snapshot=r2_saved,
        after_snapshot=r3,
        one_off={},
        rates={},
    )
    attribution = {
        "save_window": save_window_attr,
        "reopen": reopen_attr,
    }
    ignored_runtime_hours_total = float(save_window_attr.get("ignored_runtime_hours", 0.0)) + float(
        reopen_attr.get("ignored_runtime_hours", 0.0)
    )
    unrecorded_resource_by_type: dict[str, float] = {}

    # A-B gap (communication/verification gap) resource deltas:
    # A: decide to verify/report; B: verification completed and returns to operation.
    # This bucket should be excluded from "no comm-delay expected".
    r2_resources = r2.get("resources", {}) if isinstance(r2, dict) else {}
    r2_saved_resources = r2_saved.get("resources", {}) if isinstance(r2_saved, dict) else {}
    r3_resources = r3.get("resources", {}) if isinstance(r3, dict) else {}
    ab_gap_delta_save = _resource_delta_only_numeric(
        r2_resources if isinstance(r2_resources, dict) else {},
        r2_saved_resources if isinstance(r2_saved_resources, dict) else {},
    )
    ab_gap_delta_reopen = _resource_delta_only_numeric(
        r2_saved_resources if isinstance(r2_saved_resources, dict) else {},
        r3_resources if isinstance(r3_resources, dict) else {},
    )
    ab_unrecorded_by_resource: dict[str, float] = {}
    for key in RESOURCE_KEYS:
        v = float(ab_gap_delta_save.get(key, 0.0)) + float(ab_gap_delta_reopen.get(key, 0.0))
        if abs(v) > 1e-6:
            ab_unrecorded_by_resource[key] = v

    actual_final_resources = r3_resources if isinstance(r3_resources, dict) else {}
    expected_no_comm_delay_resources = _resource_subtract(actual_final_resources, ab_unrecorded_by_resource)
    expected_no_comm_delay_resources = {
        key: value for key, value in expected_no_comm_delay_resources.items() if isinstance(value, (int, float))
    }
    total_actual_resources = _resource_sum(actual_final_resources if isinstance(actual_final_resources, dict) else {})
    total_expected_no_comm_delay = _resource_sum(expected_no_comm_delay_resources)
    total_delay_impact = total_actual_resources - total_expected_no_comm_delay

    report: dict[str, Any] = {
        "test_name": "通用资源对账测试",
        "test_id": test_id,
        "generated_at": _utc_iso(),
        "phase_runs": {
            "phase1": phase1,
            "phase2": phase2,
        },
        "shared_user_data_dir": str(shared_user_data_dir),
        "snapshots": {
            "r0": r0,
            "target_a_cleaned": target_a_cleaned,
            "target_a_built": target_a_built,
            "target_b_cleaned": target_b_cleaned,
            "target_b_built": target_b_built,
            "r2": r2,
            "r2_saved": r2_saved,
            "rs": rs,
            "r3": r3,
        },
        "time_windows": {
            "cleanup_target_a": stage_cleanup_a,
            "build_target_a": stage_build_a,
            "cleanup_target_b": stage_cleanup_b,
            "build_target_b": stage_build_b,
            "operation_total": stage_total,
            "reopen": stage_reopen,
        },
        "resource_diffs": {
            "r2_saved_vs_rs": diff_r2_saved_rs,
            "rs_vs_r3": diff_rs_r3,
            "r2_saved_vs_r3": diff_r2_saved_r3,
            "r2_vs_r2_saved": diff_r2_r2_saved,
            "r0_to_r2": _diff_values(r0.get("resources", {}), r2.get("resources", {})),
        },
        "attribution_breakdown": attribution,
        "ignored_runtime_hours": {
            "total": ignored_runtime_hours_total,
            "save_window": float(save_window_attr.get("ignored_runtime_hours", 0.0)),
            "reopen": float(reopen_attr.get("ignored_runtime_hours", 0.0)),
        },
        "calculation_policy": {
            "valid_runtime_definition": "valid runtime includes explicit wait/sleep and intended gameplay progression (cleanup/build/normal running).",
            "ab_gap_definition": "A-B gap is the runtime between deciding to verify/report (A) and finishing verification then returning to operations (B).",
            "no_comm_delay_expected_rule": "expected_no_comm_delay_final = actual_final - ab_unrecorded_by_resource",
            "delay_impact_rule": "delay_impact = actual_final - expected_no_comm_delay_final",
        },
        "runtime_buckets": {
            "valid_runtime_hours": float(stage_total.get("game_hours_delta", 0.0) or 0.0),
            "ab_gap_ignored_hours": {
                "save_window": float(save_window_attr.get("ignored_runtime_hours", 0.0)),
                "reopen": float(reopen_attr.get("ignored_runtime_hours", 0.0)),
                "total": ignored_runtime_hours_total,
            },
        },
        "resource_buckets": {
            "actual_final_resources": actual_final_resources,
            "expected_no_comm_delay_final_resources": expected_no_comm_delay_resources,
            "ab_unrecorded_by_resource": ab_unrecorded_by_resource,
            "valid_delta_by_resource": _resource_delta_only_numeric(
                r0.get("resources", {}) if isinstance(r0.get("resources", {}), dict) else {},
                r2_resources if isinstance(r2_resources, dict) else {},
            ),
            "total_actual_resources": total_actual_resources,
            "total_expected_no_comm_delay_resources": total_expected_no_comm_delay,
            "total_delay_impact": total_delay_impact,
        },
        "unrecorded_resource_by_type": unrecorded_resource_by_type,
        "checks": {
            "phase1_passed": phase1.get("status") == "passed",
            "phase2_passed": phase2.get("status") == "passed",
            "save_resources_loaded": bool(rs.get("resources")),
        },
        "observations": {
            "r2_saved_vs_rs_runtime_delta": diff_r2_saved_rs,
            "rs_vs_r3_runtime_delta": diff_rs_r3,
            "r2_saved_vs_r3_runtime_delta": diff_r2_saved_r3,
            "ab_gap_delta_save_window": ab_gap_delta_save,
            "ab_gap_delta_reopen_window": ab_gap_delta_reopen,
        },
    }
    all_ok = all(bool(v) for v in report["checks"].values())
    report["status"] = "passed" if all_ok else "failed"
    gate_explanations: list[dict[str, Any]] = []
    for gate_name, gate_ok in report["checks"].items():
        ok = bool(gate_ok)
        reason = ""
        fix_hint = ""
        if gate_name == "phase1_passed":
            reason = "phase1 执行失败，通常是步骤超时或目标节点不可交互。"
            fix_hint = "检查 phase1 flow_report.json 与 driver_flow.json 最后失败 step_id。"
        elif gate_name == "phase2_passed":
            reason = "phase2 执行失败，通常是 continue 后校验步骤超时或状态不达标。"
            fix_hint = "检查 phase2 flow_report.json，确认 verify_* 相关步骤。"
        elif gate_name == "save_resources_loaded":
            reason = "未成功读取 save slot 资源，无法完成存档对账。"
            fix_hint = "检查 shared_user_data_dir/saves/slot_0.json 与 APPDATA fallback 路径。"
        gate_explanations.append(
            {
                "gate": str(gate_name),
                "gate_code": _gate_error_code(str(gate_name)),
                "ok": ok,
                "reason_if_failed": reason,
                "next_action_if_failed": fix_hint,
            }
        )
    report["gate_explanations"] = gate_explanations
    report["next_actions"] = [
        "先看 gate_explanations 中第一个 ok=false 的 gate，并按 next_action_if_failed 处理。",
        "若执行类 gate 均通过但资源差异异常，优先查看 observations.ab_gap_delta_* 是否跨结算边界。",
        "复测时保持相同流程链路与 timeout，避免把流程变更误判为系统延迟。",
    ]
    if report["status"] != "passed":
        failed_gates = [str(item.get("gate", "")) for item in gate_explanations if not bool(item.get("ok", False))]
        failed_gate_codes = [str(item.get("gate_code", "")) for item in gate_explanations if not bool(item.get("ok", False))]
        report["status_explanation"] = {
            "summary": "硬门禁失败，但已附带可执行解释与修复方向，避免后续 agent 仅看到 failed 而误解。",
            "failed_gates": failed_gates,
            "failed_gate_codes": failed_gate_codes,
        }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, (0 if all_ok else 2)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run basic data validation resource reconcile flow.")
    parser.add_argument("--project-root", required=True, help="Project root path")
    parser.add_argument(
        "--godot-bin",
        default="",
        help="Godot 可执行文件；可留空，从 GODOT_BIN 或 config/godot_executable.json 解析",
    )
    parser.add_argument("--timeout-sec", type=int, default=300, help="Timeout per phase")
    parser.add_argument("--output-json", default="", help="Report output path")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    project_root = Path(args.project_root).resolve()
    mcp_dir = Path(__file__).resolve().parents[1] / "mcp"
    if str(mcp_dir) not in sys.path:
        sys.path.insert(0, str(mcp_dir))
    from server_common import resolve_godot_bin  # noqa: E402

    godot_resolved, _meta = resolve_godot_bin(
        requested=str(args.godot_bin or "").strip(),
        strict=False,
        allow_unresolved=False,
        project_root=project_root,
    )
    output_json = (
        Path(args.output_json).resolve()
        if str(args.output_json).strip()
        else project_root / "artifacts" / "test-runs" / f"basic_data_test_report_{_utc_id()}.json"
    )
    report, code = run_basic_data_validation(
        project_root=project_root,
        godot_bin=str(godot_resolved),
        timeout_sec=int(args.timeout_sec),
        output_json=output_json,
    )
    print(json.dumps({"status": report.get("status"), "report_json": str(output_json)}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
