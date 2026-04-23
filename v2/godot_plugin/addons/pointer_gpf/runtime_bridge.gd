extends Node

const _CMD_REL := "res://pointer_gpf/tmp/command.json"
const _RSP_REL := "res://pointer_gpf/tmp/response.json"
const _TMP_DIR_REL := "res://pointer_gpf/tmp"
const _AUTO_STOP_PLAY_MODE_FLAG_REL := "res://pointer_gpf/tmp/auto_stop_play_mode.flag"
const _RUNTIME_SESSION_REL := "res://pointer_gpf/tmp/runtime_session.json"
const _RuntimeDiagnosticsWriter := preload("res://addons/pointer_gpf/runtime_diagnostics_writer.gd")
const _RuntimeDiagnosticsLogger := preload("res://addons/pointer_gpf/runtime_diagnostics_logger.gd")

var _diag_writer: RefCounted = _RuntimeDiagnosticsWriter.new()
var _diag_os_logger = null
var _last_run_id: String = ""
var _last_seq: int = -1
var _poll_accum: float = 0.0
var _automation_input_guard_active: bool = false
var _run_captures: Dictionary = {}
var _run_evidence_records: Dictionary = {}
var _active_observers: Dictionary = {}


func _ready() -> void:
    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_TMP_DIR_REL))
    if not Engine.is_editor_hint():
        _install_os_error_logger()
    _write_runtime_session()
    var tree := get_tree()
    if tree != null and not tree.scene_changed.is_connected(_on_scene_changed):
        tree.scene_changed.connect(_on_scene_changed)
    set_process(true)
    set_process_input(true)


func _exit_tree() -> void:
    if _diag_os_logger != null:
        OS.remove_logger(_diag_os_logger)
        _diag_os_logger = null
    _delete_runtime_session()


func _install_os_error_logger() -> void:
    if _diag_os_logger != null:
        return
    _diag_os_logger = _RuntimeDiagnosticsLogger.new(_diag_writer)
    OS.add_logger(_diag_os_logger)


func _process(delta: float) -> void:
    _diag_writer.tick_flush(delta)
    _apply_automation_input_guard()
    _poll_accum += delta
    if _poll_accum < 0.05:
        return
    _poll_accum = 0.0
    _poll_bridge()


func _input(event: InputEvent) -> void:
    if not _should_consume_user_input():
        return
    if event is InputEventMouseMotion or event is InputEventMouseButton:
        get_viewport().set_input_as_handled()


func _poll_bridge() -> void:
    var cmd_path := ProjectSettings.globalize_path(_CMD_REL)
    if not FileAccess.file_exists(cmd_path):
        return
    var f := FileAccess.open(cmd_path, FileAccess.READ)
    if f == null:
        return
    var data: Variant = JSON.parse_string(f.get_as_text())
    f.close()
    if typeof(data) != TYPE_DICTIONARY:
        _write_error_response("INVALID_ARGUMENT", "command must be a JSON object", -1, "")
        _delete_command_file()
        return
    var d: Dictionary = data
    var run_id := str(d.get("run_id", ""))
    if run_id != "":
        _automation_input_guard_active = true
    if run_id != _last_run_id:
        _run_captures.clear()
        _run_evidence_records.clear()
        _active_observers.clear()
    _diag_writer.reset_for_run(run_id)
    var seq := _coerce_int(d.get("seq", null))
    if seq < 0:
        _write_error_response("INVALID_ARGUMENT", "seq is required", -1, run_id)
        _delete_command_file()
        return
    if run_id == _last_run_id and seq == _last_seq:
        _write_response({"ok": true, "seq": seq, "run_id": run_id, "duplicate": true, "message": "duplicate command"})
        _delete_command_file()
        return
    var step: Dictionary = d.get("step", {}) if typeof(d.get("step", {})) == TYPE_DICTIONARY else {}
    var action := str(step.get("action", d.get("action", ""))).strip_edges()
    if action == "":
        _write_error_response("INVALID_ARGUMENT", "action is required", seq, run_id)
        _delete_command_file()
        _last_run_id = run_id
        _last_seq = seq
        return
    _last_run_id = run_id
    _last_seq = seq
    var rsp := _dispatch_action(action, seq, run_id, d, step)
    _diag_writer.note_bridge_dispatch(action, rsp)
    _write_response(rsp)
    _delete_command_file()


func _dispatch_action(action: String, seq: int, run_id: String, command: Dictionary, step: Dictionary) -> Dictionary:
    match action.to_lower():
        "launchgame":
            _enforce_visible_mouse_mode()
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "launchGame acknowledged"}
        "delay":
            var delay_ms := max(0, _coerce_int(step.get("timeoutMs", command.get("timeoutMs", 0))))
            OS.delay_msec(delay_ms)
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "delay acknowledged",
                "elapsedMs": delay_ms,
            }
        "capture":
            return _capture_runtime_value(command, step, seq, run_id)
        "sample":
            return _sample_runtime_value(command, step, seq, run_id)
        "observe":
            return _observe_runtime_event(command, step, seq, run_id)
        "click":
            var click_result := _perform_click(_extract_target(command, step), _extract_position(command, step))
            if not bool(click_result.get("ok", false)):
                return _error_payload("TARGET_NOT_FOUND", str(click_result.get("message", "target not found")), seq, run_id)
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "click acknowledged", "target": _extract_target(command, step)}
        "wait":
            var wait_hint := _extract_wait_hint(command, step)
            var timeout_ms := max(50, _coerce_int(step.get("timeoutMs", command.get("timeoutMs", 0))))
            var wait_result := _evaluate_until_hint(wait_hint, timeout_ms)
            return {
                "ok": bool(wait_result.get("conditionMet", false)),
                "seq": seq,
                "run_id": run_id,
                "message": "wait acknowledged",
                "elapsedMs": int(wait_result.get("elapsedMs", timeout_ms)),
                "conditionMet": bool(wait_result.get("conditionMet", false)),
                "hint": wait_hint,
                "reason": str(wait_result.get("reason", "")),
            }
        "check":
            var check_result := _evaluate_check(command, step)
            var check_rsp := {"ok": bool(check_result.get("passed", false)), "seq": seq, "run_id": run_id, "message": "check acknowledged", "details": check_result}
            var evidence_ref := str(check_result.get("evidence_ref", "")).strip_edges()
            if evidence_ref != "" and _run_evidence_records.has(evidence_ref):
                check_rsp["runtime_evidence_refs"] = [evidence_ref]
                check_rsp["runtime_evidence_records"] = [_run_evidence_records[evidence_ref]]
            return check_rsp
        "snapshot":
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "snapshot acknowledged"}
        "closeproject":
            if _execution_mode() == "isolated_runtime":
                call_deferred("_quit_runtime_process")
            elif not _request_stop_play_mode():
                return _error_payload("STOP_FLAG_WRITE_FAILED", "could not write auto_stop_play_mode.flag", seq, run_id)
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "closeProject acknowledged"}
        _:
            return _error_payload("ACTION_NOT_SUPPORTED", "unsupported action: %s" % action, seq, run_id)


func _extract_target(command: Dictionary, step: Dictionary) -> Variant:
    if step.has("target"):
        return step.get("target")
    return command.get("target", "")


func _extract_position(command: Dictionary, step: Dictionary) -> Vector2:
    var target := _extract_target(command, step)
    if typeof(target) == TYPE_DICTIONARY:
        var td: Dictionary = target
        return Vector2(float(td.get("x", 0.0)), float(td.get("y", 0.0)))
    return Vector2.ZERO


func _extract_wait_hint(command: Dictionary, step: Dictionary) -> String:
    var until := step.get("until", command.get("until", null))
    if typeof(until) == TYPE_DICTIONARY:
        var ud: Dictionary = until
        return str(ud.get("hint", "")).strip_edges()
    return str(step.get("hint", command.get("hint", ""))).strip_edges()


func _evaluate_check(command: Dictionary, step: Dictionary) -> Dictionary:
    var hint := str(step.get("hint", command.get("hint", ""))).strip_edges()
    var target := _extract_target(command, step)
    var evidence_ref := str(step.get("evidenceRef", step.get("evidence_ref", command.get("evidenceRef", command.get("evidence_ref", ""))))).strip_edges()
    if evidence_ref != "":
        return _evaluate_evidence_check(evidence_ref, _extract_predicate(command, step))
    var capture_key := str(step.get("captureKey", command.get("captureKey", ""))).strip_edges()
    var metric := str(step.get("metric", command.get("metric", "rotation_y"))).strip_edges()
    if capture_key != "":
        return _evaluate_capture_check(target, capture_key, metric, _coerce_tolerance(step.get("tolerance", command.get("tolerance", 0.001))))
    var passed := true
    var reason := "ok"
    if hint != "" and _is_machine_hint(hint):
        var eval := _evaluate_hint_once(hint)
        passed = bool(eval.get("matched", false))
        reason = str(eval.get("reason", "hint evaluation"))
    elif typeof(target) == TYPE_DICTIONARY:
        var td: Dictionary = target
        var target_hint := str(td.get("hint", "")).strip_edges()
        if target_hint != "":
            var eval_target := _evaluate_hint_once(target_hint)
            passed = bool(eval_target.get("matched", false))
            reason = str(eval_target.get("reason", "target evaluation"))
    return {"status": "ok" if passed else "failed", "hint": hint, "passed": passed, "reason": reason}


func _extract_evidence_key(command: Dictionary, step: Dictionary) -> String:
    return str(step.get("evidenceKey", step.get("evidence_ref", step.get("evidenceRef", command.get("evidenceKey", ""))))).strip_edges()


func _extract_metric(command: Dictionary, step: Dictionary) -> Variant:
    if step.has("metric"):
        return step.get("metric")
    return command.get("metric", "rotation_y")


func _extract_predicate(command: Dictionary, step: Dictionary) -> Dictionary:
    var predicate := step.get("predicate", command.get("predicate", {}))
    return predicate if typeof(predicate) == TYPE_DICTIONARY else {}


func _sample_runtime_value(command: Dictionary, step: Dictionary, seq: int, run_id: String) -> Dictionary:
    var evidence_key := _extract_evidence_key(command, step)
    if evidence_key == "":
        return _error_payload("INVALID_ARGUMENT", "evidenceKey is required for sample action", seq, run_id)
    var target := _extract_target(command, step)
    var metric := _extract_metric(command, step)
    var window_ms := max(0, _coerce_int(step.get("windowMs", command.get("windowMs", 0))))
    var interval_ms := max(16, _coerce_int(step.get("intervalMs", command.get("intervalMs", 50))))
    var node := _resolve_target_node_with_retry(target, 1200)
    if node == null:
        return _error_payload("TARGET_NOT_FOUND", "cannot resolve sample target", seq, run_id)
    var samples: Array = []
    var start := Time.get_ticks_msec()
    var elapsed := 0
    while elapsed <= window_ms:
        var read_result := _read_runtime_metric(node, metric)
        var sample := {
            "timestamp_ms": elapsed,
            "ok": bool(read_result.get("ok", false)),
            "value": read_result.get("value", null),
            "value_type": str(read_result.get("value_type", "")),
        }
        if not bool(read_result.get("ok", false)):
            sample["message"] = str(read_result.get("message", "read failed"))
        samples.append(sample)
        if elapsed >= window_ms:
            break
        OS.delay_msec(interval_ms)
        elapsed = Time.get_ticks_msec() - start
    var status := "passed"
    for item in samples:
        if typeof(item) == TYPE_DICTIONARY and not bool((item as Dictionary).get("ok", false)):
            status = "inconclusive"
            break
    var record := {
        "evidence_id": evidence_key,
        "record_type": "sample_result",
        "status": status,
        "target": _target_description(target, node),
        "metric": _metric_description(metric),
        "window_ms": window_ms,
        "interval_ms": interval_ms,
        "samples": samples,
    }
    _run_evidence_records[evidence_key] = record
    return {
        "ok": status == "passed",
        "seq": seq,
        "run_id": run_id,
        "message": "sample acknowledged",
        "runtime_evidence_refs": [evidence_key],
        "runtime_evidence_records": [record],
    }


func _observe_runtime_event(command: Dictionary, step: Dictionary, seq: int, run_id: String) -> Dictionary:
    var evidence_key := _extract_evidence_key(command, step)
    if evidence_key == "":
        return _error_payload("INVALID_ARGUMENT", "evidenceKey is required for observe action", seq, run_id)
    var mode := str(step.get("mode", command.get("mode", "window"))).strip_edges().to_lower()
    if mode == "collect":
        if not _active_observers.has(evidence_key):
            return _error_payload("EVENT_OBSERVER_NOT_FOUND", "no active observer exists for evidence key: %s" % evidence_key, seq, run_id)
        var observer_for_collect_any = _active_observers.get(evidence_key, {})
        if typeof(observer_for_collect_any) != TYPE_DICTIONARY:
            return _error_payload("EVENT_OBSERVER_INVALID", "active observer state is invalid", seq, run_id)
        var observer_for_collect: Dictionary = observer_for_collect_any
        var setup_for_collect: Dictionary = observer_for_collect.get("setup", {})
        _stop_observer(evidence_key, setup_for_collect)
        var collected_record := _build_observer_record(evidence_key, observer_for_collect)
        _run_evidence_records[evidence_key] = collected_record
        _active_observers.erase(evidence_key)
        return {
            "ok": true,
            "seq": seq,
            "run_id": run_id,
            "message": "observe collect acknowledged",
            "runtime_evidence_refs": [evidence_key],
            "runtime_evidence_records": [collected_record],
        }
    var event_spec := step.get("event", command.get("event", {}))
    if typeof(event_spec) != TYPE_DICTIONARY:
        return _error_payload("INVALID_ARGUMENT", "event object is required for observe action", seq, run_id)
    var event_dict: Dictionary = event_spec
    var event_kind := str(event_dict.get("kind", "")).strip_edges()
    var window_ms := max(16, _coerce_int(step.get("windowMs", command.get("windowMs", 250))))
    if _active_observers.has(evidence_key):
        return _error_payload("EVENT_OBSERVER_ALREADY_ACTIVE", "an observer already exists for evidence key: %s" % evidence_key, seq, run_id)
    _active_observers[evidence_key] = {
        "events": [],
        "kind": event_kind,
        "event_kind": event_kind,
        "window_ms": window_ms,
        "started_at_ms": Time.get_ticks_msec(),
    }
    var setup := _start_observer(evidence_key, event_dict, _extract_target(command, step))
    if not bool(setup.get("ok", false)):
        _active_observers.erase(evidence_key)
        return _error_payload("EVENT_NOT_SUPPORTED", str(setup.get("message", "event not supported")), seq, run_id)
    var active_observer: Dictionary = _active_observers[evidence_key]
    active_observer["setup"] = setup
    _active_observers[evidence_key] = active_observer
    if mode == "start":
        return {
            "ok": true,
            "seq": seq,
            "run_id": run_id,
            "message": "observe start acknowledged",
            "runtime_evidence_refs": [evidence_key],
        }
    OS.delay_msec(window_ms)
    _stop_observer(evidence_key, setup)
    var observer := _active_observers.get(evidence_key, {})
    var record := _build_observer_record(evidence_key, observer if typeof(observer) == TYPE_DICTIONARY else {})
    _run_evidence_records[evidence_key] = record
    _active_observers.erase(evidence_key)
    return {
        "ok": true,
        "seq": seq,
        "run_id": run_id,
        "message": "observe acknowledged",
        "runtime_evidence_refs": [evidence_key],
        "runtime_evidence_records": [record],
    }


func _build_observer_record(evidence_key: String, observer: Dictionary) -> Dictionary:
    var events := observer.get("events", [])
    var window_ms := max(0, _coerce_int(observer.get("window_ms", 0)))
    var started_at_ms := max(0, _coerce_int(observer.get("started_at_ms", 0)))
    return {
        "evidence_id": evidence_key,
        "record_type": "event_observer_result",
        "status": "passed",
        "event_kind": str(observer.get("event_kind", observer.get("kind", ""))).strip_edges(),
        "window_ms": window_ms,
        "started_at_ms": started_at_ms,
        "collected_at_ms": Time.get_ticks_msec(),
        "events": events if typeof(events) == TYPE_ARRAY else [],
    }


func _start_observer(evidence_key: String, event_spec: Dictionary, target: Variant) -> Dictionary:
    var event_kind := str(event_spec.get("kind", "")).strip_edges()
    if event_kind == "scene_changed":
        var tree := get_tree()
        if tree == null:
            return {"ok": false, "message": "scene tree is not available"}
        var cb := Callable(self, "_on_observed_scene_changed").bind(evidence_key)
        if not tree.scene_changed.is_connected(cb):
            tree.scene_changed.connect(cb)
        return {"ok": true, "source": tree, "signal": "scene_changed", "callable": cb}
    var node := _resolve_target_node_with_retry(target, 1200)
    if node == null:
        return {"ok": false, "message": "cannot resolve observe target"}
    if event_kind == "animation_started" or event_kind == "animation_finished":
        if not (node is AnimationPlayer):
            return {"ok": false, "message": "animation observation requires an AnimationPlayer target"}
        var signal_name := "animation_started" if event_kind == "animation_started" else "animation_finished"
        var cb_anim := Callable(self, "_on_observed_animation_event").bind(evidence_key, event_kind)
        if not node.is_connected(signal_name, cb_anim):
            node.connect(signal_name, cb_anim)
        return {"ok": true, "source": node, "signal": signal_name, "callable": cb_anim}
    if event_kind == "signal_emitted":
        var signal_name_any := str(event_spec.get("signal_name", "")).strip_edges()
        if signal_name_any == "":
            return {"ok": false, "message": "signal_name is required for signal_emitted observation"}
        if not node.has_signal(signal_name_any):
            return {"ok": false, "message": "target does not define signal: %s" % signal_name_any}
        var cb_signal := Callable(self, "_on_observed_signal_event").bind(evidence_key, signal_name_any)
        if not node.is_connected(signal_name_any, cb_signal):
            node.connect(signal_name_any, cb_signal)
        return {"ok": true, "source": node, "signal": signal_name_any, "callable": cb_signal}
    return {"ok": false, "message": "unsupported event kind: %s" % event_kind}


func _stop_observer(_evidence_key: String, setup: Dictionary) -> void:
    var source = setup.get("source", null)
    var signal_name := str(setup.get("signal", "")).strip_edges()
    var cb: Callable = setup.get("callable", Callable())
    if source != null and signal_name != "" and cb.is_valid() and source.is_connected(signal_name, cb):
        source.disconnect(signal_name, cb)


func _append_observed_event(evidence_key: String, payload: Dictionary) -> void:
    if not _active_observers.has(evidence_key):
        return
    var observer: Dictionary = _active_observers[evidence_key]
    var events: Array = observer.get("events", [])
    payload["timestamp_ms"] = Time.get_ticks_msec()
    events.append(payload)
    observer["events"] = events
    _active_observers[evidence_key] = observer


func _on_observed_scene_changed(evidence_key: String) -> void:
    var scene_path := ""
    var tree := get_tree()
    if tree != null and tree.current_scene != null:
        scene_path = str(tree.current_scene.scene_file_path)
    _append_observed_event(evidence_key, {"event": "scene_changed", "scene": scene_path})


func _on_observed_animation_event(animation_name: StringName, evidence_key: String, event_kind: String) -> void:
    _append_observed_event(evidence_key, {"event": event_kind, "animation_name": str(animation_name)})


func _on_observed_signal_event(arg1: Variant = null, arg2: Variant = null, arg3: Variant = null, arg4: Variant = null, arg5: Variant = null, arg6: Variant = null, arg7: Variant = null) -> void:
    var args := [arg1, arg2, arg3, arg4, arg5, arg6, arg7]
    var evidence_key := ""
    var signal_name := ""
    var payload_args: Array = []
    for i in range(args.size()):
        var candidate := str(args[i])
        if evidence_key == "" and _active_observers.has(candidate):
            evidence_key = candidate
            if i + 1 < args.size():
                signal_name = str(args[i + 1])
            payload_args = args.slice(0, i)
            break
    if evidence_key == "":
        return
    _append_observed_event(evidence_key, {"event": "signal_emitted", "signal_name": signal_name, "args": _serialize_array(payload_args)})


func _evaluate_evidence_check(evidence_ref: String, predicate: Dictionary) -> Dictionary:
    if not _run_evidence_records.has(evidence_ref):
        return {"status": "failed", "passed": false, "reason": "evidence_ref not found", "evidence_ref": evidence_ref}
    var record: Dictionary = _run_evidence_records[evidence_ref]
    var passed := _evaluate_predicate(record, predicate)
    var status := "ok" if passed else "failed"
    return {"status": status, "passed": passed, "reason": "evidence predicate", "evidence_ref": evidence_ref, "predicate": predicate}


func _evaluate_predicate(record: Dictionary, predicate: Dictionary) -> bool:
    var operator := str(predicate.get("operator", "")).strip_edges()
    if operator == "":
        return str(record.get("status", "")).strip_edges() == "passed"
    if operator == "event_count_at_least":
        var events := record.get("events", [])
        var min_count := max(0, _coerce_int(predicate.get("count", 1)))
        return typeof(events) == TYPE_ARRAY and (events as Array).size() >= min_count
    if operator == "sample_count_at_least":
        var samples := record.get("samples", [])
        var min_samples := max(0, _coerce_int(predicate.get("count", 1)))
        return typeof(samples) == TYPE_ARRAY and (samples as Array).size() >= min_samples
    if operator == "not_equals":
        return _sample_value_changed(record)
    if operator == "changed_from_baseline":
        return _sample_value_changed(record)
    if operator == "returned_to_baseline":
        return _sample_value_returned(record)
    return str(record.get("status", "")).strip_edges() == "passed"


func _sample_value_changed(record: Dictionary) -> bool:
    var samples := record.get("samples", [])
    if typeof(samples) != TYPE_ARRAY or (samples as Array).size() < 2:
        return false
    var first: Variant = (samples as Array)[0]
    if typeof(first) != TYPE_DICTIONARY:
        return false
    var baseline := JSON.stringify((first as Dictionary).get("value", null))
    for item in samples:
        if typeof(item) == TYPE_DICTIONARY and JSON.stringify((item as Dictionary).get("value", null)) != baseline:
            return true
    return false


func _sample_value_returned(record: Dictionary) -> bool:
    var samples := record.get("samples", [])
    if typeof(samples) != TYPE_ARRAY or (samples as Array).size() < 3:
        return false
    var first: Variant = (samples as Array)[0]
    var last: Variant = (samples as Array)[(samples as Array).size() - 1]
    if typeof(first) != TYPE_DICTIONARY or typeof(last) != TYPE_DICTIONARY:
        return false
    return JSON.stringify((first as Dictionary).get("value", null)) == JSON.stringify((last as Dictionary).get("value", null)) and _sample_value_changed(record)


func _capture_runtime_value(command: Dictionary, step: Dictionary, seq: int, run_id: String) -> Dictionary:
    var capture_key := str(step.get("captureKey", command.get("captureKey", ""))).strip_edges()
    if capture_key == "":
        return _error_payload("INVALID_ARGUMENT", "captureKey is required for capture action", seq, run_id)
    var target := _extract_target(command, step)
    var metric := str(step.get("metric", command.get("metric", "rotation_y"))).strip_edges()
    var node := _resolve_target_node_with_retry(target, 1200)
    if node == null:
        return _error_payload("TARGET_NOT_FOUND", "cannot resolve capture target", seq, run_id)
    var metric_result := _read_metric_from_node(node, metric)
    if not bool(metric_result.get("ok", false)):
        return _error_payload("METRIC_NOT_SUPPORTED", str(metric_result.get("message", "metric not supported")), seq, run_id)
    _run_captures[capture_key] = {
        "metric": metric,
        "value": metric_result.get("value", 0.0),
        "node_path": str(node.get_path()) if node.is_inside_tree() else "",
    }
    return {
        "ok": true,
        "seq": seq,
        "run_id": run_id,
        "message": "capture acknowledged",
        "captureKey": capture_key,
        "metric": metric,
        "value": metric_result.get("value", 0.0),
    }


func _evaluate_capture_check(target: Variant, capture_key: String, metric: String, tolerance: float) -> Dictionary:
    if not _run_captures.has(capture_key):
        return {
            "status": "failed",
            "hint": "",
            "passed": false,
            "reason": "capture key not found",
            "captureKey": capture_key,
        }
    var node := _resolve_target_node_with_retry(target, 1200)
    if node == null:
        return {
            "status": "failed",
            "hint": "",
            "passed": false,
            "reason": "capture target not found",
            "captureKey": capture_key,
        }
    var metric_result := _read_metric_from_node(node, metric)
    if not bool(metric_result.get("ok", false)):
        return {
            "status": "failed",
            "hint": "",
            "passed": false,
            "reason": str(metric_result.get("message", "metric not supported")),
            "captureKey": capture_key,
        }
    var baseline := _run_captures.get(capture_key, {})
    var baseline_value := float((baseline as Dictionary).get("value", 0.0))
    var current_value := float(metric_result.get("value", 0.0))
    var delta := absf(current_value - baseline_value)
    var passed := delta <= tolerance
    return {
        "status": "ok" if passed else "failed",
        "hint": "",
        "passed": passed,
        "reason": "capture comparison",
        "captureKey": capture_key,
        "metric": metric,
        "baselineValue": baseline_value,
        "currentValue": current_value,
        "delta": delta,
        "tolerance": tolerance,
    }


func _read_metric_from_node(node: Node, metric: String) -> Dictionary:
    match metric:
        "rotation_y":
            if node is Node3D:
                return {"ok": true, "value": float((node as Node3D).rotation.y)}
            return {"ok": false, "message": "rotation_y requires a Node3D target"}
        "global_rotation_y":
            if node is Node3D:
                return {"ok": true, "value": float((node as Node3D).global_rotation.y)}
            return {"ok": false, "message": "global_rotation_y requires a Node3D target"}
        _:
            return {"ok": false, "message": "unsupported metric: %s" % metric}


func _read_runtime_metric(node: Node, metric: Variant) -> Dictionary:
    if typeof(metric) == TYPE_STRING:
        var legacy := _read_metric_from_node(node, str(metric))
        if bool(legacy.get("ok", false)):
            legacy["value"] = _serialize_variant_value(legacy.get("value", null))
            legacy["value_type"] = "float"
        return legacy
    if typeof(metric) != TYPE_DICTIONARY:
        return {"ok": false, "message": "metric must be a string or object"}
    var metric_dict: Dictionary = metric
    var kind := str(metric_dict.get("kind", "")).strip_edges()
    if kind == "node_property":
        var property_path := str(metric_dict.get("property_path", metric_dict.get("propertyPath", ""))).strip_edges()
        if property_path == "":
            return {"ok": false, "message": "node_property metric requires property_path"}
        var value = node.get_indexed(NodePath(property_path))
        return {"ok": true, "value": _serialize_variant_value(value), "value_type": _variant_type_name(value)}
    if kind == "shader_param":
        var param_name := str(metric_dict.get("param_name", metric_dict.get("parameter", ""))).strip_edges()
        if param_name == "":
            return {"ok": false, "message": "shader_param metric requires param_name"}
        if not (node is CanvasItem):
            return {"ok": false, "message": "shader_param metric requires a CanvasItem target"}
        var material := (node as CanvasItem).material
        if not (material is ShaderMaterial):
            return {"ok": false, "message": "target material is not a ShaderMaterial"}
        var shader_value = (material as ShaderMaterial).get_shader_parameter(param_name)
        return {"ok": true, "value": _serialize_variant_value(shader_value), "value_type": _variant_type_name(shader_value)}
    if kind == "animation_state":
        if not (node is AnimationPlayer):
            return {"ok": false, "message": "animation_state metric requires an AnimationPlayer target"}
        var player := node as AnimationPlayer
        return {
            "ok": true,
            "value": {
                "current_animation": str(player.current_animation),
                "is_playing": bool(player.is_playing()),
                "current_animation_position": float(player.current_animation_position),
            },
            "value_type": "dictionary",
        }
    if kind == "node_exists":
        return {"ok": true, "value": true, "value_type": "bool"}
    if kind == "signal_connection_exists":
        var signal_name := str(metric_dict.get("signal_name", "")).strip_edges()
        var method_name := str(metric_dict.get("method_name", "")).strip_edges()
        if signal_name == "":
            return {"ok": false, "message": "signal_connection_exists requires signal_name"}
        var exists := false
        for item in node.get_signal_connection_list(signal_name):
            if typeof(item) != TYPE_DICTIONARY:
                continue
            var callable: Callable = (item as Dictionary).get("callable", Callable())
            if method_name == "" or callable.get_method() == method_name:
                exists = true
                break
        return {"ok": true, "value": exists, "value_type": "bool"}
    return {"ok": false, "message": "unsupported metric kind: %s" % kind}


func _target_description(target: Variant, node: Node) -> Dictionary:
    return {
        "hint": str((target as Dictionary).get("hint", "")) if typeof(target) == TYPE_DICTIONARY else str(target),
        "node_path": str(node.get_path()) if node != null and node.is_inside_tree() else "",
    }


func _metric_description(metric: Variant) -> Variant:
    if typeof(metric) == TYPE_DICTIONARY:
        return metric
    return str(metric)


func _serialize_array(values: Array) -> Array:
    var out: Array = []
    for value in values:
        out.append(_serialize_variant_value(value))
    return out


func _serialize_variant_value(value: Variant) -> Variant:
    match typeof(value):
        TYPE_NIL:
            return null
        TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING:
            return value
        TYPE_STRING_NAME:
            return str(value)
        TYPE_VECTOR2:
            var v2 := value as Vector2
            return {"x": v2.x, "y": v2.y}
        TYPE_VECTOR3:
            var v3 := value as Vector3
            return {"x": v3.x, "y": v3.y, "z": v3.z}
        TYPE_COLOR:
            var c := value as Color
            return {"r": c.r, "g": c.g, "b": c.b, "a": c.a}
        TYPE_ARRAY:
            return _serialize_array(value as Array)
        TYPE_DICTIONARY:
            var out := {}
            for key in (value as Dictionary).keys():
                out[str(key)] = _serialize_variant_value((value as Dictionary)[key])
            return out
        _:
            return str(value)


func _variant_type_name(value: Variant) -> String:
    match typeof(value):
        TYPE_NIL:
            return "nil"
        TYPE_BOOL:
            return "bool"
        TYPE_INT:
            return "int"
        TYPE_FLOAT:
            return "float"
        TYPE_STRING:
            return "string"
        TYPE_STRING_NAME:
            return "string_name"
        TYPE_VECTOR2:
            return "vector2"
        TYPE_VECTOR3:
            return "vector3"
        TYPE_COLOR:
            return "color"
        TYPE_ARRAY:
            return "array"
        TYPE_DICTIONARY:
            return "dictionary"
        _:
            return "variant"


func _perform_click(target: Variant, fallback_pos: Vector2) -> Dictionary:
    _enforce_visible_mouse_mode()
    var node := _resolve_target_node_with_retry(target, 1200)
    if node != null:
        if node is BaseButton:
            var btn := node as BaseButton
            btn.call_deferred("emit_signal", "pressed")
            return {"ok": true, "node_path": str(btn.get_path()) if btn.is_inside_tree() else ""}
        if node is Control:
            var ctrl := node as Control
            _dispatch_click_virtual(ctrl.get_global_rect().position + (ctrl.get_global_rect().size / 2.0))
            return {"ok": true, "node_path": str(ctrl.get_path()) if ctrl.is_inside_tree() else ""}
        _dispatch_click_virtual(fallback_pos)
        return {"ok": true, "node_path": str(node.get_path()) if node.is_inside_tree() else ""}
    if fallback_pos != Vector2.ZERO:
        _dispatch_click_virtual(fallback_pos)
        return {"ok": true, "node_path": ""}
    return {"ok": false, "message": "cannot resolve clickable target"}


func _resolve_target_node_with_retry(target: Variant, timeout_ms: int = 1200) -> Node:
    var start := Time.get_ticks_msec()
    var timeout_safe := max(0, timeout_ms)
    while true:
        var node := _resolve_target_node(target)
        if node != null:
            return node
        if Time.get_ticks_msec() - start >= timeout_safe:
            return null
        OS.delay_msec(16)
    return null


func _resolve_target_node(target: Variant) -> Node:
    if typeof(target) == TYPE_DICTIONARY:
        var td: Dictionary = target
        var hint := str(td.get("hint", "")).strip_edges()
        if hint != "":
            return _resolve_node_by_hint(hint)
    elif typeof(target) == TYPE_STRING:
        var raw := str(target).strip_edges()
        if raw != "":
            return _resolve_node_by_hint(raw)
    return null


func _resolve_node_by_hint(hint: String) -> Node:
    var token := _normalize_hint_token(hint)
    if token == "":
        return null
    var tree := get_tree()
    if tree == null:
        return null
    var scene := tree.current_scene
    if scene != null:
        var by_path := scene.get_node_or_null(NodePath(token))
        if by_path != null:
            return by_path
    var queue: Array = [scene] if scene != null else [tree.root]
    while queue.size() > 0:
        var node := queue.pop_front() as Node
        if node == null:
            continue
        if _node_matches_token(node, token):
            return node
        for child in node.get_children():
            if child is Node:
                queue.append(child)
    return null


func _normalize_hint_token(hint: String) -> String:
    var raw := hint.strip_edges()
    if raw.begins_with("node_name:"):
        return raw.substr("node_name:".length()).strip_edges()
    if raw.begins_with("node_exists:"):
        return raw.substr("node_exists:".length()).strip_edges()
    if raw.begins_with("node_visible:"):
        return raw.substr("node_visible:".length()).strip_edges()
    if raw.begins_with("node_hidden:"):
        return raw.substr("node_hidden:".length()).strip_edges()
    return raw


func _is_machine_hint(hint: String) -> bool:
    return hint.find(":") > 0


func _node_matches_token(node: Node, token: String) -> bool:
    var name_low := str(node.name).to_lower()
    var token_low := token.to_lower()
    if name_low == token_low:
        return true
    if name_low.find(token_low) >= 0:
        return true
    return str(node.get_path()).to_lower().find(token_low) >= 0


func _evaluate_until_hint(hint: String, timeout_ms: int) -> Dictionary:
    var start := Time.get_ticks_msec()
    var timeout_safe := max(50, timeout_ms)
    var elapsed := 0
    var last_reason := "timeout"
    while elapsed <= timeout_safe:
        var result := _evaluate_hint_once(hint)
        if bool(result.get("matched", false)):
            return {"conditionMet": true, "elapsedMs": elapsed, "reason": str(result.get("reason", "matched"))}
        last_reason = str(result.get("reason", "timeout"))
        OS.delay_msec(16)
        elapsed = Time.get_ticks_msec() - start
    return {"conditionMet": false, "elapsedMs": timeout_safe, "reason": last_reason}


func _evaluate_hint_once(hint: String) -> Dictionary:
    var raw := hint.strip_edges()
    if raw == "":
        return {"matched": true, "reason": "empty hint treated as pass"}
    if raw.to_lower() == "runtime_alive":
        return {"matched": true, "reason": "runtime bridge active"}
    var expect_visible := raw.begins_with("node_visible:")
    var expect_hidden := raw.begins_with("node_hidden:")
    var node := _resolve_node_by_hint(raw)
    if node == null:
        if expect_hidden:
            return {"matched": true, "reason": "node not found treated as hidden"}
        return {"matched": false, "reason": "node not found"}
    if expect_visible or expect_hidden:
        if node is CanvasItem:
            var vis := bool((node as CanvasItem).is_visible_in_tree())
            if expect_visible:
                return {"matched": vis, "reason": "node visibility"}
            return {"matched": not vis, "reason": "node hidden state"}
    return {"matched": true, "reason": "node exists"}


func _dispatch_click_virtual(pos: Vector2, button_index: int = MOUSE_BUTTON_LEFT) -> void:
    var down := InputEventMouseButton.new()
    down.position = pos
    down.button_index = button_index
    down.pressed = true
    Input.parse_input_event(down)
    var up := InputEventMouseButton.new()
    up.position = pos
    up.button_index = button_index
    up.pressed = false
    Input.parse_input_event(up)


func _apply_automation_input_guard() -> void:
    if not _automation_input_guard_active:
        return
    _enforce_visible_mouse_mode()
    _force_pointer_ui_mode_on_players()


func _should_consume_user_input() -> bool:
    return _automation_input_guard_active and _execution_mode() == "isolated_runtime"


func _on_scene_changed() -> void:
    if not _automation_input_guard_active:
        return
    _enforce_visible_mouse_mode()
    _force_pointer_ui_mode_on_players()
    call_deferred("_enforce_visible_mouse_mode")
    call_deferred("_force_pointer_ui_mode_on_players")


func _enforce_visible_mouse_mode() -> void:
    # Automated runs should not seize the user's mouse through captured-mode gameplay scripts.
    if Input.mouse_mode != Input.MOUSE_MODE_VISIBLE:
        Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _force_pointer_ui_mode_on_players() -> void:
    if not _automation_input_guard_active:
        return
    var tree := get_tree()
    if tree == null:
        return
    for node in tree.get_nodes_in_group("player"):
        if node == null:
            continue
        if "pointer_ui_mode" in node:
            node.pointer_ui_mode = true


func _request_stop_play_mode() -> bool:
    var request_path := ProjectSettings.globalize_path(_AUTO_STOP_PLAY_MODE_FLAG_REL)
    DirAccess.make_dir_recursive_absolute(request_path.get_base_dir())
    var out := FileAccess.open(request_path, FileAccess.WRITE)
    if out == null:
        return false
    out.store_string(JSON.stringify({"schema": "pointer_gpf.v2.auto_stop.v1", "issued_at_unix": Time.get_unix_time_from_system()}))
    out.close()
    return true


func _quit_runtime_process() -> void:
    var tree := get_tree()
    if tree != null:
        tree.quit()


func _write_response(payload: Dictionary) -> void:
    var rsp_path := ProjectSettings.globalize_path(_RSP_REL)
    DirAccess.make_dir_recursive_absolute(rsp_path.get_base_dir())
    var out := FileAccess.open(rsp_path, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(JSON.stringify(payload))
    out.close()


func _write_error_response(code: String, message: String, seq: int, run_id: String) -> void:
    _write_response(_error_payload(code, message, seq, run_id))


func _error_payload(code: String, message: String, seq: int, run_id: String) -> Dictionary:
    return {"ok": false, "seq": seq, "run_id": run_id, "code": code, "message": message}


func _delete_command_file() -> void:
    var cmd_path := ProjectSettings.globalize_path(_CMD_REL)
    if FileAccess.file_exists(cmd_path):
        DirAccess.remove_absolute(cmd_path)


func _coerce_int(v: Variant) -> int:
    match typeof(v):
        TYPE_INT:
            return v
        TYPE_FLOAT:
            return int(v)
        _:
            return -1


func _coerce_tolerance(v: Variant) -> float:
    match typeof(v):
        TYPE_INT:
            return float(v)
        TYPE_FLOAT:
            return float(v)
        _:
            return 0.001


func _execution_mode() -> String:
    var mode := OS.get_environment("POINTER_GPF_EXECUTION_MODE").strip_edges()
    if mode == "":
        return "play_mode"
    return mode


func _write_runtime_session() -> void:
    var session_path := ProjectSettings.globalize_path(_RUNTIME_SESSION_REL)
    DirAccess.make_dir_recursive_absolute(session_path.get_base_dir())
    var out := FileAccess.open(session_path, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(
        JSON.stringify(
            {
                "schema": "pointer_gpf.v2.runtime_session.v1",
                "execution_mode": _execution_mode(),
                "process_id": OS.get_process_id(),
                "desktop_name": OS.get_environment("POINTER_GPF_RUNTIME_DESKTOP"),
            }
        )
    )
    out.close()


func _delete_runtime_session() -> void:
    var session_path := ProjectSettings.globalize_path(_RUNTIME_SESSION_REL)
    if FileAccess.file_exists(session_path):
        DirAccess.remove_absolute(session_path)
