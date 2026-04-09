extends Node
## Polls `res://pointer_gpf/tmp/command.json` and writes `response.json` for MCP flow execution.

const _CMD_REL := "res://pointer_gpf/tmp/command.json"
const _RSP_REL := "res://pointer_gpf/tmp/response.json"
const _TMP_DIR_REL := "res://pointer_gpf/tmp"

var _last_run_id: String = ""
var _last_seq: int = -1
var _poll_accum: float = 0.0


func _ready() -> void:
    var tmp_global := ProjectSettings.globalize_path(_TMP_DIR_REL)
    DirAccess.make_dir_recursive_absolute(tmp_global)
    set_process(true)


func _process(delta: float) -> void:
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
    var text := f.get_as_text()
    f.close()
    var data: Variant = JSON.parse_string(text)
    if typeof(data) != TYPE_DICTIONARY:
        _write_error_response("INVALID_ARGUMENT", "command must be a JSON object", -1, "")
        _delete_command_file()
        return
    var d: Dictionary = data
    var run_id := str(d.get("run_id", ""))
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
    match key:
        "launchgame":
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "launchGame acknowledged"}
        "click":
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "click acknowledged",
                "target": _extract_target(command, step),
            }
        "wait":
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "wait acknowledged",
                "elapsedMs": max(0, _coerce_int(step.get("timeoutMs", command.get("timeoutMs", 0)))),
                "conditionMet": true,
            }
        "check":
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "check acknowledged",
                "details": {"status": "ok", "kind": str(step.get("kind", command.get("kind", "")))},
            }
        "snapshot":
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "snapshot acknowledged",
                "artifactPath": str(step.get("artifactPath", command.get("artifactPath", "user://pointer_gpf_snapshot.png"))),
            }
        _:
            return _error_payload("ACTION_NOT_SUPPORTED", "unsupported action: %s" % action, seq, run_id)


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
