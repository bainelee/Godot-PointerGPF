extends RefCounted

const SCHEMA := "pointer_gpf.v2.runtime_diagnostics.v1"
const _OUT_REL := "res://pointer_gpf/tmp/runtime_diagnostics.json"

var _items: Array = []
var _severity: String = "info"
var _summary: String = ""
var _tracked_run_id: String = ""
var _flush_accum: float = 0.0
const _FLUSH_INTERVAL := 0.2
var _pending_engine_errors: Array = []
var _log_mutex: Mutex = Mutex.new()


func reset_for_run(run_id: String) -> void:
    if run_id == "":
        return
    if run_id != _tracked_run_id:
        _tracked_run_id = run_id
        _items.clear()
        _severity = "info"
        _summary = ""
        _log_mutex.lock()
        _pending_engine_errors.clear()
        _log_mutex.unlock()


func enqueue_engine_error(rationale: String, file_path: String, line_no: int, stack_text: String) -> void:
    _log_mutex.lock()
    _pending_engine_errors.append({"r": rationale, "f": file_path, "l": line_no, "s": stack_text})
    _log_mutex.unlock()


func note_bridge_dispatch(action: String, response: Dictionary) -> void:
    var ok: bool = bool(response.get("ok", false))
    var msg: String = str(response.get("message", ""))
    var code: String = str(response.get("code", ""))
    var kind := "bridge_ok" if ok else "bridge_error"
    if not ok and code != "":
        msg = "%s: %s" % [code, msg]
    _items.append({"kind": kind, "message": "%s — %s" % [action, msg], "file": "", "line": 0, "stack": ""})
    while _items.size() > 40:
        _items.pop_front()
    if not ok:
        _severity = "error"
        _summary = msg
    elif _severity != "error":
        _summary = "bridge idle"


func tick_flush(delta: float) -> void:
    _drain_engine_errors()
    _flush_accum += delta
    if _flush_accum < _FLUSH_INTERVAL:
        return
    _flush_accum = 0.0
    _write_disk()


func _drain_engine_errors() -> void:
    _log_mutex.lock()
    var batch := _pending_engine_errors.duplicate()
    _pending_engine_errors.clear()
    _log_mutex.unlock()
    for raw in batch:
        if typeof(raw) != TYPE_DICTIONARY:
            continue
        var d: Dictionary = raw
        _items.append(
            {
                "kind": "engine_log_error",
                "message": str(d.get("r", "")),
                "file": str(d.get("f", "")),
                "line": int(d.get("l", 0)),
                "stack": str(d.get("s", "")),
            }
        )
        while _items.size() > 40:
            _items.pop_front()
        _severity = "error"
        _summary = str(d.get("r", ""))


func _write_disk() -> void:
    var path_global := ProjectSettings.globalize_path(_OUT_REL)
    DirAccess.make_dir_recursive_absolute(path_global.get_base_dir())
    var payload := {
        "schema": SCHEMA,
        "updated_at": Time.get_datetime_string_from_system(false, true),
        "source": "game_runtime",
        "severity": _severity,
        "summary": _summary,
        "items": _items.duplicate(true),
    }
    var out := FileAccess.open(path_global, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(JSON.stringify(payload))
    out.close()

