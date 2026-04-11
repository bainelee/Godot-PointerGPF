extends Node

const _CMD_REL := "res://pointer_gpf/tmp/command.json"
const _RSP_REL := "res://pointer_gpf/tmp/response.json"
const _TMP_DIR_REL := "res://pointer_gpf/tmp"
const _AUTO_STOP_PLAY_MODE_FLAG_REL := "res://pointer_gpf/tmp/auto_stop_play_mode.flag"
const _RuntimeDiagnosticsWriter := preload("res://addons/pointer_gpf/runtime_diagnostics_writer.gd")
const _RuntimeDiagnosticsLogger := preload("res://addons/pointer_gpf/runtime_diagnostics_logger.gd")

var _diag_writer: RefCounted = _RuntimeDiagnosticsWriter.new()
var _diag_os_logger = null
var _last_run_id: String = ""
var _last_seq: int = -1
var _poll_accum: float = 0.0


func _ready() -> void:
    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_TMP_DIR_REL))
    if not Engine.is_editor_hint():
        _install_os_error_logger()
    set_process(true)


func _exit_tree() -> void:
    if _diag_os_logger != null:
        OS.remove_logger(_diag_os_logger)
        _diag_os_logger = null


func _install_os_error_logger() -> void:
    if _diag_os_logger != null:
        return
    _diag_os_logger = _RuntimeDiagnosticsLogger.new(_diag_writer)
    OS.add_logger(_diag_os_logger)


func _process(delta: float) -> void:
    _diag_writer.tick_flush(delta)
    _poll_accum += delta
    if _poll_accum < 0.05:
        return
    _poll_accum = 0.0
    _poll_bridge()


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
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "launchGame acknowledged"}
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
            return {"ok": bool(check_result.get("passed", false)), "seq": seq, "run_id": run_id, "message": "check acknowledged", "details": check_result}
        "snapshot":
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "snapshot acknowledged"}
        "closeproject":
            if not _request_stop_play_mode():
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


func _perform_click(target: Variant, fallback_pos: Vector2) -> Dictionary:
    var node := _resolve_target_node_with_retry(target, 1200)
    if node != null:
        if node is BaseButton:
            var btn := node as BaseButton
            if btn.has_method("grab_focus"):
                btn.grab_focus()
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


func _request_stop_play_mode() -> bool:
    var request_path := ProjectSettings.globalize_path(_AUTO_STOP_PLAY_MODE_FLAG_REL)
    DirAccess.make_dir_recursive_absolute(request_path.get_base_dir())
    var out := FileAccess.open(request_path, FileAccess.WRITE)
    if out == null:
        return false
    out.store_string(JSON.stringify({"schema": "pointer_gpf.v2.auto_stop.v1", "issued_at_unix": Time.get_unix_time_from_system()}))
    out.close()
    return true


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
