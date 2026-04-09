extends Node
## Polls `res://pointer_gpf/tmp/command.json` and writes `response.json` for MCP flow execution.

const _CMD_REL := "res://pointer_gpf/tmp/command.json"
const _RSP_REL := "res://pointer_gpf/tmp/response.json"
const _TMP_DIR_REL := "res://pointer_gpf/tmp"

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
        _write_error_response("INVALID_COMMAND_FORMAT", "command must be a JSON object", -1, "")
        _delete_command_file()
        return
    var d: Dictionary = data
    var run_id := str(d.get("run_id", ""))
    var seq_raw: Variant = d.get("seq", null)
    var seq: int = _coerce_int(seq_raw)
    if seq < 0:
        _write_error_response("INVALID_SEQUENCE", "seq is required and must be int/float", -1, run_id)
        _delete_command_file()
        return
    if seq == _last_seq:
        return
    var step: Variant = d.get("step", {})
    if typeof(step) != TYPE_DICTIONARY:
        step = {}
    var action := str((step as Dictionary).get("action", ""))
    if action.strip_edges() == "":
        _write_error_response("MISSING_ACTION", "step.action is required", seq, run_id)
        _delete_command_file()
        _last_seq = seq
        return
    _last_seq = seq
    var rsp := _dispatch_action(action, seq, run_id, step as Dictionary)
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


func _dispatch_action(action: String, seq: int, run_id: String, _step: Dictionary) -> Dictionary:
    var key := action.to_lower()
    match key:
        "launchgame":
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "launchGame acknowledged"}
        "click":
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "click acknowledged"}
        "wait":
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "wait acknowledged"}
        "check":
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "check acknowledged"}
        "snapshot":
            return {"ok": true, "seq": seq, "run_id": run_id, "message": "snapshot acknowledged"}
        _:
            return {
                "ok": false,
                "seq": seq,
                "run_id": run_id,
                "code": "ACTION_NOT_SUPPORTED",
                "message": "unsupported action: %s" % action,
            }


func _write_response(rsp: Dictionary) -> void:
    var rsp_path := ProjectSettings.globalize_path(_RSP_REL)
    var out := FileAccess.open(rsp_path, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(JSON.stringify(rsp))
    out.close()


func _write_error_response(code: String, message: String, seq: int, run_id: String) -> void:
    _write_response(
        {
            "ok": false,
            "code": code,
            "message": message,
            "seq": seq,
            "run_id": run_id,
        }
    )


func _delete_command_file() -> void:
    var cmd_path := ProjectSettings.globalize_path(_CMD_REL)
    if not FileAccess.file_exists(cmd_path):
        return
    var err := DirAccess.remove_absolute(cmd_path)
    if err != OK:
        # Ignore cleanup failure; next poll will retry.
        pass
