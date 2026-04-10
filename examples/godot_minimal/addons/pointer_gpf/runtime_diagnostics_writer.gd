extends RefCounted
## Persists MCP-visible runtime diagnostics to res://pointer_gpf/tmp/runtime_diagnostics.json (atomic tmp + replace).

const SCHEMA := "pointer_gpf.runtime_diagnostics.v1"
const _OUT_REL := "res://pointer_gpf/tmp/runtime_diagnostics.json"

var _items: Array = []
var _severity: String = "info"
var _summary: String = ""
var _flush_accum: float = 0.0
const _FLUSH_INTERVAL := 0.2
var _tracked_run_id: String = ""
var _log_mutex: Mutex = Mutex.new()
var _pending_engine_errors: Array = []


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
    _pending_engine_errors.append(
        {"r": rationale, "f": file_path, "l": line_no, "s": stack_text}
    )
    _log_mutex.unlock()


func drain_engine_error_queue() -> void:
    _log_mutex.lock()
    var batch: Array = _pending_engine_errors.duplicate()
    _pending_engine_errors.clear()
    _log_mutex.unlock()
    for raw in batch:
        if typeof(raw) != TYPE_DICTIONARY:
            continue
        var d: Dictionary = raw
        var entry: Dictionary = {
            "kind": "engine_log_error",
            "message": str(d.get("r", "")),
            "file": str(d.get("f", "")),
            "line": int(d.get("l", 0)),
            "stack": str(d.get("s", "")),
        }
        _items.append(entry)
        while _items.size() > 40:
            _items.pop_front()
        _severity = "error"
        _summary = str(entry["message"])


func note_bridge_dispatch(action: String, response: Dictionary) -> void:
    var ok: bool = bool(response.get("ok", false))
    var msg: String = str(response.get("message", ""))
    var code: String = str(response.get("code", ""))
    var kind: String = "bridge_ok" if ok else "bridge_error"
    if not ok and code != "":
        msg = "%s: %s" % [code, msg]
    var entry: Dictionary = {
        "kind": kind,
        "message": "%s — %s" % [action, msg],
        "file": "",
        "line": 0,
        "stack": "",
    }
    _items.append(entry)
    while _items.size() > 40:
        _items.pop_front()
    if not ok:
        _severity = "error"
        _summary = msg
    elif _severity != "error":
        _summary = "bridge idle"


func tick_flush(delta: float) -> void:
    drain_engine_error_queue()
    _flush_accum += delta
    if _flush_accum < _FLUSH_INTERVAL:
        return
    _flush_accum = 0.0
    _write_disk()


func _iso_now() -> String:
    return Time.get_datetime_string_from_system(false, true)


func _write_disk() -> void:
    var path_global: String = ProjectSettings.globalize_path(_OUT_REL)
    var base_dir: String = path_global.get_base_dir()
    DirAccess.make_dir_recursive_absolute(base_dir)
    var payload: Dictionary = {
        "schema": SCHEMA,
        "updated_at": _iso_now(),
        "source": "game_runtime",
        "severity": _severity,
        "summary": _summary,
        "items": _items.duplicate(true),
    }
    var json_text: String = JSON.stringify(payload)
    var tmp_path: String = path_global + ".tmp"
    var f: FileAccess = FileAccess.open(tmp_path, FileAccess.WRITE)
    if f == null:
        return
    f.store_string(json_text)
    f.close()
    if FileAccess.file_exists(path_global):
        DirAccess.remove_absolute(path_global)
    var err: Error = DirAccess.rename_absolute(tmp_path, path_global)
    if err != OK:
        var fb: FileAccess = FileAccess.open(path_global, FileAccess.WRITE)
        if fb != null:
            fb.store_string(json_text)
            fb.close()
