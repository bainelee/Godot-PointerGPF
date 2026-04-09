@tool
extends EditorPlugin

const _TMP_DIR_REL := "res://pointer_gpf/tmp"
const _RUNTIME_GATE_REL := "res://pointer_gpf/tmp/runtime_gate.json"
const _AUTO_ENTER_PLAY_MODE_FLAG_REL := "res://pointer_gpf/tmp/auto_enter_play_mode.flag"
const _AUTO_STOP_PLAY_MODE_FLAG_REL := "res://pointer_gpf/tmp/auto_stop_play_mode.flag"
const _RUNTIME_AUTOLOAD_NAME := "PointerGPFRuntimeBridge"
const _RUNTIME_AUTOLOAD_PATH := "res://addons/pointer_gpf/runtime_bridge.gd"

var _gate_sync_accum: float = 0.0


func _enter_tree() -> void:
    add_autoload_singleton(_RUNTIME_AUTOLOAD_NAME, _RUNTIME_AUTOLOAD_PATH)
    _sync_runtime_gate_marker()
    set_process(true)


func _process(delta: float) -> void:
    _gate_sync_accum += delta
    if _gate_sync_accum < 0.2:
        return
    _gate_sync_accum = 0.0
    _handle_auto_enter_play_request()
    _handle_auto_stop_play_request()
    _sync_runtime_gate_marker()


func _exit_tree() -> void:
    _write_runtime_gate_marker(
        {
            "runtime_mode": "editor_bridge",
            "runtime_entry": "unknown",
            "runtime_gate_passed": false,
        }
    )
    remove_autoload_singleton(_RUNTIME_AUTOLOAD_NAME)
    set_process(false)


func _sync_runtime_gate_marker() -> void:
    var playing_scene := bool(EditorInterface.is_playing_scene())
    _write_runtime_gate_marker(
        {
            "runtime_mode": "play_mode" if playing_scene else "editor_bridge",
            "runtime_entry": "already_running_play_session" if playing_scene else "unknown",
            "runtime_gate_passed": playing_scene,
        }
    )


func _handle_auto_enter_play_request() -> void:
    if bool(EditorInterface.is_playing_scene()):
        return
    var request_path := ProjectSettings.globalize_path(_AUTO_ENTER_PLAY_MODE_FLAG_REL)
    if not FileAccess.file_exists(request_path):
        return
    var _cleanup_err := DirAccess.remove_absolute(request_path)
    EditorInterface.play_main_scene()


func _handle_auto_stop_play_request() -> void:
    var request_path := ProjectSettings.globalize_path(_AUTO_STOP_PLAY_MODE_FLAG_REL)
    if not FileAccess.file_exists(request_path):
        return
    var _cleanup_err := DirAccess.remove_absolute(request_path)
    if not bool(EditorInterface.is_playing_scene()):
        return
    EditorInterface.stop_playing_scene()


func _write_runtime_gate_marker(payload: Dictionary) -> void:
    var tmp_global := ProjectSettings.globalize_path(_TMP_DIR_REL)
    DirAccess.make_dir_recursive_absolute(tmp_global)
    var marker_path := ProjectSettings.globalize_path(_RUNTIME_GATE_REL)
    var out := FileAccess.open(marker_path, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(JSON.stringify(payload))
    out.close()
