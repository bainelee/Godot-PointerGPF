extends Node
## Polls `res://pointer_gpf/tmp/command.json` and writes `response.json` for MCP flow execution.

const _CMD_REL := "res://pointer_gpf/tmp/command.json"
const _RSP_REL := "res://pointer_gpf/tmp/response.json"
const _TMP_DIR_REL := "res://pointer_gpf/tmp"
const _READY_REL := "res://pointer_gpf/tmp/runtime_bridge_ready.json"
const _AUTO_STOP_PLAY_MODE_FLAG_REL := "res://pointer_gpf/tmp/auto_stop_play_mode.flag"
const _RuntimeDiagnosticsWriter := preload("res://addons/pointer_gpf/runtime_diagnostics_writer.gd")
const _RuntimeDiagnosticsLogger := preload("res://addons/pointer_gpf/runtime_diagnostics_logger.gd")

var _diag_writer: RefCounted = _RuntimeDiagnosticsWriter.new()
var _diag_os_logger = null
var _last_run_id: String = ""
var _last_seq: int = -1
var _poll_accum: float = 0.0
var _virtual_cursor_layer: CanvasLayer
var _virtual_cursor_rect: ColorRect
var _cursor_visible_until_msec: int = 0


func _ready() -> void:
    var tmp_global := ProjectSettings.globalize_path(_TMP_DIR_REL)
    DirAccess.make_dir_recursive_absolute(tmp_global)
    _write_ready_marker()
    _setup_virtual_cursor_overlay()
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
        _hide_virtual_cursor_if_needed()
        return
    _poll_accum = 0.0
    _poll_bridge()
    _hide_virtual_cursor_if_needed()


func _poll_bridge() -> void:
    var cmd_path := ProjectSettings.globalize_path(_CMD_REL)
    if not FileAccess.file_exists(cmd_path):
        return
    var f := FileAccess.open(cmd_path, FileAccess.READ)
    if f == null:
        return
    var text := f.get_as_text()
    f.close()
    var data: Variant = JSON.parse_string(text)
    if typeof(data) != TYPE_DICTIONARY:
        _write_error_response("INVALID_ARGUMENT", "command must be a JSON object", -1, "")
        _delete_command_file()
        return
    var d: Dictionary = data
    var run_id := str(d.get("run_id", ""))
    _diag_writer.reset_for_run(run_id)
    var seq_raw: Variant = d.get("seq", null)
    var seq: int = _coerce_int(seq_raw)
    if seq < 0:
        _write_error_response("INVALID_ARGUMENT", "seq is required and must be int/float", -1, run_id)
        _delete_command_file()
        return
    if run_id == _last_run_id and seq == _last_seq:
        _write_response(
            {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "duplicate": true,
                "message": "duplicate command (same run_id+seq already processed)",
            }
        )
        _delete_command_file()
        return
    var step: Variant = d.get("step", {})
    if typeof(step) != TYPE_DICTIONARY:
        step = {}
    var action := _resolve_action(d, step as Dictionary)
    if action.strip_edges() == "":
        _write_error_response("INVALID_ARGUMENT", "action is required (supports top-level action or step.action)", seq, run_id)
        _delete_command_file()
        _last_run_id = run_id
        _last_seq = seq
        return
    _last_run_id = run_id
    _last_seq = seq
    var rsp := _dispatch_action(action, seq, run_id, d, step as Dictionary)
    _diag_writer.note_bridge_dispatch(action, rsp)
    _write_response(rsp)
    _delete_command_file()


func _coerce_int(v: Variant) -> int:
    match typeof(v):
        TYPE_INT:
            return v
        TYPE_FLOAT:
            return int(v)
        _:
            return -1


func _resolve_action(command: Dictionary, step: Dictionary) -> String:
    var top_level_action := str(command.get("action", "")).strip_edges()
    if top_level_action != "":
        return top_level_action
    return str(step.get("action", "")).strip_edges()


func _extract_target(command: Dictionary, step: Dictionary) -> Variant:
    if step.has("target"):
        return step.get("target")
    return command.get("target", "")


func _dispatch_action(action: String, seq: int, run_id: String, command: Dictionary, step: Dictionary) -> Dictionary:
    var key := action.to_lower()
    if _requires_os_level_input(key):
        return _error_payload("INPUT_PATH_BLOCKED", "input path cannot guarantee os isolation", seq, run_id)
    match key:
        "launchgame":
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "launchGame acknowledged"}
        "click":
            var click_result := _perform_click(_extract_target(command, step), _extract_position(command, step))
            if not bool(click_result.get("ok", false)):
                return _error_payload("TARGET_NOT_FOUND", str(click_result.get("message", "target not found")), seq, run_id)
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "click acknowledged",
                "target": _extract_target(command, step),
                "resolved_node": click_result.get("node_path", ""),
            }
        "movemouse":
            _dispatch_move_mouse_virtual(_extract_position(command, step))
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "moveMouse acknowledged",
                "target": _extract_target(command, step),
            }
        "drag":
            _dispatch_drag_virtual(_extract_position(command, step), _extract_end_position(command, step))
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "drag acknowledged",
                "target": _extract_target(command, step),
            }
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
            return {
                "ok": bool(check_result.get("passed", false)),
                "seq": seq,
                "run_id": run_id,
                "message": "check acknowledged",
                "details": check_result,
            }
        "snapshot":
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "snapshot acknowledged",
                "artifactPath": str(step.get("artifactPath", command.get("artifactPath", "user://pointer_gpf_snapshot.png"))),
            }
        "closeproject", "stopgametestsession":
            if not _request_stop_play_mode():
                return _error_payload(
                    "STOP_FLAG_WRITE_FAILED",
                    "could not write auto_stop_play_mode.flag",
                    seq,
                    run_id
                )
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "closeProject acknowledged",
            }
        _:
            return _error_payload("ACTION_NOT_SUPPORTED", "unsupported action: %s" % action, seq, run_id)


func _extract_wait_hint(command: Dictionary, step: Dictionary) -> String:
    var until := step.get("until", command.get("until", null))
    if typeof(until) == TYPE_DICTIONARY:
        var ud: Dictionary = until
        return str(ud.get("hint", "")).strip_edges()
    return str(step.get("hint", command.get("hint", ""))).strip_edges()


func _evaluate_check(command: Dictionary, step: Dictionary) -> Dictionary:
    var kind := str(step.get("kind", command.get("kind", "")))
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
    elif hint != "":
        # Human-readable check text without machine hint should not be treated as lookup key.
        passed = true
        reason = "no_machine_assertion_hint"
    return {"status": "ok" if passed else "failed", "kind": kind, "hint": hint, "passed": passed, "reason": reason}


func _perform_click(target: Variant, fallback_pos: Vector2) -> Dictionary:
    var node := _resolve_target_node_with_retry(target, 1200)
    if node != null:
        if node is BaseButton:
            var btn := node as BaseButton
            var reported_path := str(btn.get_path()) if btn.is_inside_tree() else ""
            var click_pos := _control_center(btn)
            _activate_button(btn, click_pos)
            return {"ok": true, "node_path": reported_path}
        if node is Control:
            var ctrl := node as Control
            var reported_path_c := str(ctrl.get_path()) if ctrl.is_inside_tree() else ""
            var click_pos_c := _control_center(ctrl)
            _dispatch_click_virtual(click_pos_c)
            return {"ok": true, "node_path": reported_path_c}
        var reported_path_n := str(node.get_path()) if node.is_inside_tree() else ""
        _dispatch_click_virtual(fallback_pos)
        return {"ok": true, "node_path": reported_path_n}
    if fallback_pos != Vector2.ZERO:
        _dispatch_click_virtual(fallback_pos)
        return {"ok": true, "node_path": ""}
    return {"ok": false, "message": "cannot resolve clickable target"}


func _activate_button(btn: BaseButton, click_pos: Vector2) -> void:
    _show_virtual_cursor(click_pos)
    if btn == null:
        return
    if btn.has_method("grab_focus"):
        btn.grab_focus()
    # BaseButton targets are more reliable when we trigger a single deferred pressed signal
    # instead of relying purely on synthetic mouse input or double-firing the handler.
    btn.call_deferred("emit_signal", "pressed")


func _resolve_target_node_with_retry(target: Variant, timeout_ms: int = 1200) -> Node:
    var timeout_safe := max(0, timeout_ms)
    var start := Time.get_ticks_msec()
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
    if raw == "":
        return ""
    if raw.begins_with("node_name:"):
        return raw.substr("node_name:".length()).strip_edges()
    if raw.begins_with("name_token:"):
        return raw.substr("name_token:".length()).strip_edges()
    if raw.begins_with("node_exists:"):
        return raw.substr("node_exists:".length()).strip_edges()
    if raw.begins_with("node_visible:"):
        return raw.substr("node_visible:".length()).strip_edges()
    if raw.begins_with("node_hidden:"):
        return raw.substr("node_hidden:".length()).strip_edges()
    if raw == "main_scene_ready":
        return "/root"
    if raw == "start_or_continue_button":
        return "start"
    if raw == "in_game_hud_ready":
        return "ui"
    if raw == "save_game_entry":
        return "save"
    if raw == "load_game_entry":
        return "load"
    return raw


func _is_machine_hint(hint: String) -> bool:
    var raw := hint.strip_edges()
    if raw == "":
        return false
    if raw.find(":") > 0:
        return true
    return raw in [
        "main_scene_ready",
        "start_or_continue_button",
        "in_game_hud_ready",
        "save_game_entry",
        "load_game_entry",
    ]


func _node_matches_token(node: Node, token: String) -> bool:
    var name_low := str(node.name).to_lower()
    var token_low := token.to_lower()
    if name_low == token_low:
        return true
    if name_low.find(token_low) >= 0:
        return true
    var path_low := str(node.get_path()).to_lower()
    return path_low.find(token_low) >= 0


func _control_center(ctrl: Control) -> Vector2:
    return ctrl.get_global_rect().position + (ctrl.get_global_rect().size / 2.0)


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


func _setup_virtual_cursor_overlay() -> void:
    _virtual_cursor_layer = CanvasLayer.new()
    _virtual_cursor_layer.name = "PointerGPFVirtualCursorLayer"
    _virtual_cursor_layer.layer = 256
    add_child(_virtual_cursor_layer)

    _virtual_cursor_rect = ColorRect.new()
    _virtual_cursor_rect.name = "PointerGPFVirtualCursor"
    _virtual_cursor_rect.color = Color(1, 0, 0, 0.95)
    _virtual_cursor_rect.size = Vector2(8, 8)
    _virtual_cursor_rect.visible = false
    _virtual_cursor_layer.add_child(_virtual_cursor_rect)


func _hide_virtual_cursor_if_needed() -> void:
    if _virtual_cursor_rect == null:
        return
    if not _virtual_cursor_rect.visible:
        return
    if Time.get_ticks_msec() >= _cursor_visible_until_msec:
        _hide_virtual_cursor()


func _show_virtual_cursor(pos: Vector2, min_visible_ms: int = 120) -> void:
    if _virtual_cursor_rect == null:
        return
    _virtual_cursor_rect.position = pos - Vector2(4, 4)
    _virtual_cursor_rect.visible = true
    _cursor_visible_until_msec = Time.get_ticks_msec() + max(0, min_visible_ms)


func _hide_virtual_cursor() -> void:
    if _virtual_cursor_rect == null:
        return
    _virtual_cursor_rect.visible = false


func _extract_position(command: Dictionary, step: Dictionary) -> Vector2:
    var target := _extract_target(command, step)
    if typeof(target) == TYPE_DICTIONARY:
        var td: Dictionary = target
        var x := float(td.get("x", 0.0))
        var y := float(td.get("y", 0.0))
        return Vector2(x, y)
    if typeof(target) == TYPE_ARRAY:
        var arr: Array = target
        if arr.size() >= 2:
            return Vector2(float(arr[0]), float(arr[1]))
    if typeof(target) == TYPE_STRING:
        var s := str(target).strip_edges()
        if s.contains(","):
            var parts := s.split(",", false, 2)
            if parts.size() == 2:
                return Vector2(float(parts[0]), float(parts[1]))
    return Vector2(0, 0)


func _extract_end_position(command: Dictionary, step: Dictionary) -> Vector2:
    var endpoint := step.get("to", command.get("to", null))
    if typeof(endpoint) == TYPE_DICTIONARY:
        var ep: Dictionary = endpoint
        return Vector2(float(ep.get("x", 0.0)), float(ep.get("y", 0.0)))
    return _extract_position(command, step)


func _dispatch_move_mouse_virtual(pos: Vector2) -> void:
    _show_virtual_cursor(pos)
    var ev := InputEventMouseMotion.new()
    ev.position = pos
    ev.relative = Vector2.ZERO
    Input.parse_input_event(ev)


func _dispatch_click_virtual(pos: Vector2, button_index: int = MOUSE_BUTTON_LEFT) -> void:
    _show_virtual_cursor(pos)
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


func _dispatch_drag_virtual(start_pos: Vector2, end_pos: Vector2, button_index: int = MOUSE_BUTTON_LEFT) -> void:
    _show_virtual_cursor(start_pos)
    var down := InputEventMouseButton.new()
    down.position = start_pos
    down.button_index = button_index
    down.pressed = true
    Input.parse_input_event(down)

    var motion := InputEventMouseMotion.new()
    motion.position = end_pos
    motion.relative = end_pos - start_pos
    Input.parse_input_event(motion)
    _show_virtual_cursor(end_pos, 180)

    var up := InputEventMouseButton.new()
    up.position = end_pos
    up.button_index = button_index
    up.pressed = false
    Input.parse_input_event(up)


func _requires_os_level_input(action: String) -> bool:
    return action in ["nativehotkey", "globalmouse", "systeminput"]


func _write_response(rsp: Dictionary) -> void:
    var rsp_path := ProjectSettings.globalize_path(_RSP_REL)
    var out := FileAccess.open(rsp_path, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(JSON.stringify(rsp))
    out.close()


func _write_error_response(code: String, message: String, seq: int, run_id: String) -> void:
    _write_response(_error_payload(code, message, seq, run_id))


func _error_payload(code: String, message: String, seq: int, run_id: String) -> Dictionary:
    return {"ok": false, "seq": seq, "run_id": run_id, "error": {"code": code, "message": message}}


func _delete_command_file() -> void:
    var cmd_path := ProjectSettings.globalize_path(_CMD_REL)
    if not FileAccess.file_exists(cmd_path):
        return
    var err := DirAccess.remove_absolute(cmd_path)
    if err != OK:
        # Ignore cleanup failure; next poll will retry.
        pass


func _request_stop_play_mode() -> bool:
    var request_path := ProjectSettings.globalize_path(_AUTO_STOP_PLAY_MODE_FLAG_REL)
    var out := FileAccess.open(request_path, FileAccess.WRITE)
    if out == null:
        return false
    out.store_string(
        JSON.stringify(
            {
                "requested_by": "runtime_bridge",
                "issued_at_unix": Time.get_unix_time_from_system(),
            }
        )
    )
    out.close()
    return true


func _write_ready_marker() -> void:
    var ready_path := ProjectSettings.globalize_path(_READY_REL)
    var out := FileAccess.open(ready_path, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(
        JSON.stringify(
            {
                "schema": "pointer_gpf.runtime_bridge_ready.v1",
                "ts_unix": Time.get_unix_time_from_system(),
                "engine_is_editor_hint": Engine.is_editor_hint(),
            }
        )
    )
    out.close()
