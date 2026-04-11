@tool
extends EditorPlugin

const _TMP_DIR_REL := "res://pointer_gpf/tmp"
const _RUNTIME_GATE_REL := "res://pointer_gpf/tmp/runtime_gate.json"
const _AUTO_ENTER_PLAY_MODE_FLAG_REL := "res://pointer_gpf/tmp/auto_enter_play_mode.flag"
const _AUTO_STOP_PLAY_MODE_FLAG_REL := "res://pointer_gpf/tmp/auto_stop_play_mode.flag"
var _gate_sync_accum: float = 0.0


func _enter_tree() -> void:
    _remove_flag(_AUTO_STOP_PLAY_MODE_FLAG_REL)
    _sync_runtime_gate_marker()
    set_process(true)


func _exit_tree() -> void:
    _write_runtime_gate_marker(false, "plugin_exit")
    set_process(false)


func _process(delta: float) -> void:
    _handle_auto_stop_play_request()
    _gate_sync_accum += delta
    if _gate_sync_accum < 0.2:
        return
    _gate_sync_accum = 0.0
    _handle_auto_enter_play_request()
    _sync_runtime_gate_marker()


func _handle_auto_enter_play_request() -> void:
    if bool(EditorInterface.is_playing_scene()):
        return
    var request_path := ProjectSettings.globalize_path(_AUTO_ENTER_PLAY_MODE_FLAG_REL)
    if not FileAccess.file_exists(request_path):
        return
    DirAccess.remove_absolute(request_path)
    EditorInterface.play_main_scene()


func _handle_auto_stop_play_request() -> void:
    var request_path := ProjectSettings.globalize_path(_AUTO_STOP_PLAY_MODE_FLAG_REL)
    if not FileAccess.file_exists(request_path):
        return
    DirAccess.remove_absolute(request_path)
    if bool(EditorInterface.is_playing_scene()):
        EditorInterface.stop_playing_scene()


func _sync_runtime_gate_marker() -> void:
    _write_runtime_gate_marker(bool(EditorInterface.is_playing_scene()), "editor_poll")


func _write_runtime_gate_marker(passed: bool, runtime_mode: String) -> void:
    var tmp_global := ProjectSettings.globalize_path(_TMP_DIR_REL)
    DirAccess.make_dir_recursive_absolute(tmp_global)
    var marker_path := ProjectSettings.globalize_path(_RUNTIME_GATE_REL)
    var out := FileAccess.open(marker_path, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(
        JSON.stringify(
            {
                "schema": "pointer_gpf.v2.runtime_gate.v1",
                "runtime_mode": "play_mode" if passed else runtime_mode,
                "runtime_gate_passed": passed,
            }
        )
    )
    out.close()


func _remove_flag(rel_path: String) -> void:
    var path := ProjectSettings.globalize_path(rel_path)
    if FileAccess.file_exists(path):
        DirAccess.remove_absolute(path)
