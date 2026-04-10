@tool
extends EditorPlugin

const _TMP_DIR_REL := "res://pointer_gpf/tmp"
const _RUNTIME_GATE_REL := "res://pointer_gpf/tmp/runtime_gate.json"
const _AUTO_ENTER_PLAY_MODE_FLAG_REL := "res://pointer_gpf/tmp/auto_enter_play_mode.flag"
const _AUTO_STOP_PLAY_MODE_FLAG_REL := "res://pointer_gpf/tmp/auto_stop_play_mode.flag"
const _MCP_BOOTSTRAP_SESSION_REL := "res://pointer_gpf/tmp/mcp_bootstrap_session.json"
const _RUNTIME_AUTOLOAD_NAME := "PointerGPFRuntimeBridge"
const _RUNTIME_AUTOLOAD_PATH := "res://addons/pointer_gpf/runtime_bridge.gd"
const _TEARDOWN_DEBUG_GAME_LAST_REL := "res://pointer_gpf/tmp/teardown_debug_game_last.json"
## MCP 写入的停止标志应在短时间窗内被消费（见 `_STOP_FLAG_MAX_AGE_SEC`）；残留或无效文件会导致用户按 F5 后立即被插件停 Play（窗口一闪即关）。
const _STOP_FLAG_MAX_AGE_SEC := 45.0
## 允许 `issued_at_unix` 略晚于本机时间（对时误差），超过则视为无效。
const _STOP_FLAG_MAX_CLOCK_SKEW_SEC := 5.0

var _gate_sync_accum: float = 0.0
var _was_playing_scene: bool = false
var _pending_debug_stop_retries: int = 0


func _enter_tree() -> void:
    add_autoload_singleton(_RUNTIME_AUTOLOAD_NAME, _RUNTIME_AUTOLOAD_PATH)
    _remove_auto_stop_play_flag_on_editor_load()
    _clear_teardown_debug_game_failure_file()
    _sync_runtime_gate_marker()
    set_process(true)


func _process(delta: float) -> void:
    # 新一次 Play 开始时清掉可能残留的 auto_stop 标志，避免上次 MCP closeProject 写入的文件仍在 45s 窗内，导致本次手动 F5 立刻被 stop_playing（窗口一闪即关）。
    var playing_now := bool(EditorInterface.is_playing_scene())
    if playing_now and not _was_playing_scene:
        _remove_auto_stop_play_flag_on_editor_load()
    _was_playing_scene = playing_now

    # Stop-Play 请求由 MCP closeProject 写入标志；每帧检查以免最多卡 200ms 才响应。
    _handle_auto_stop_play_request()

    _gate_sync_accum += delta
    if _gate_sync_accum < 0.2:
        return
    _gate_sync_accum = 0.0
    _handle_auto_enter_play_request()
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


## 编辑器加载本插件时无条件删除 stop 标志，避免上次会话/MCP 异常留下的文件误伤手动 F5。
func _remove_auto_stop_play_flag_on_editor_load() -> void:
    var request_path := ProjectSettings.globalize_path(_AUTO_STOP_PLAY_MODE_FLAG_REL)
    if not FileAccess.file_exists(request_path):
        return
    var _e := DirAccess.remove_absolute(request_path)


func _handle_auto_stop_play_request() -> void:
    var request_path := ProjectSettings.globalize_path(_AUTO_STOP_PLAY_MODE_FLAG_REL)
    if not FileAccess.file_exists(request_path):
        return
    var now := Time.get_unix_time_from_system()
    var f_rd := FileAccess.open(request_path, FileAccess.READ)
    if f_rd == null:
        var _e_rd := DirAccess.remove_absolute(request_path)
        return
    var text := f_rd.get_as_text()
    f_rd.close()
    var should_stop := false
    var data: Variant = JSON.parse_string(text)
    if typeof(data) == TYPE_DICTIONARY:
        var d: Dictionary = data
        var issued := float(d.get("issued_at_unix", -1.0))
        var age := now - issued
        if issued > 0.0 and age >= -_STOP_FLAG_MAX_CLOCK_SKEW_SEC and age <= _STOP_FLAG_MAX_AGE_SEC:
            should_stop = true
    if not should_stop:
        var _drop := DirAccess.remove_absolute(request_path)
        return
    var _cleanup_err := DirAccess.remove_absolute(request_path)
    if not bool(EditorInterface.is_playing_scene()):
        return
    EditorInterface.stop_playing_scene()
    # 必须结束 (DEBUG) 游戏测试窗口：多帧重试；仍真则写入 MCP 可读的 teardown 证据文件。
    _pending_debug_stop_retries = 5
    call_deferred("_deferred_chain_stop_debug_game_session")


func _deferred_chain_stop_debug_game_session() -> void:
    if not bool(EditorInterface.is_playing_scene()):
        _clear_teardown_debug_game_failure_file()
        _write_teardown_debug_game_success_file()
        _pending_debug_stop_retries = 0
        return
    if _pending_debug_stop_retries <= 0:
        _write_teardown_debug_game_failure_file("is_playing_scene_still_true_after_stop_retries")
        _pending_debug_stop_retries = 0
        return
    _pending_debug_stop_retries -= 1
    EditorInterface.stop_playing_scene()
    call_deferred("_deferred_chain_stop_debug_game_session")


func _clear_teardown_debug_game_failure_file() -> void:
    var p := ProjectSettings.globalize_path(_TEARDOWN_DEBUG_GAME_LAST_REL)
    if FileAccess.file_exists(p):
        var _e := DirAccess.remove_absolute(p)


func _write_teardown_debug_game_success_file() -> void:
    var p := ProjectSettings.globalize_path(_TEARDOWN_DEBUG_GAME_LAST_REL)
    var dir := p.get_base_dir()
    DirAccess.make_dir_recursive_absolute(dir)
    var out := FileAccess.open(p, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(
        JSON.stringify(
            {
                "schema": "pointer_gpf.teardown_debug_game.v1",
                "ok": true,
                "reason": "stop_playing_scene_completed",
                "stopped_at_unix": Time.get_unix_time_from_system(),
            }
        )
    )
    out.close()


func _write_teardown_debug_game_failure_file(reason: String) -> void:
    var p := ProjectSettings.globalize_path(_TEARDOWN_DEBUG_GAME_LAST_REL)
    var dir := p.get_base_dir()
    DirAccess.make_dir_recursive_absolute(dir)
    var out := FileAccess.open(p, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(
        JSON.stringify(
            {
                "schema": "pointer_gpf.teardown_debug_game.v1",
                "ok": false,
                "reason": reason,
                "stopped_at_unix": Time.get_unix_time_from_system(),
            }
        )
    )
    out.close()


func _read_bootstrap_session_id() -> String:
    var p := ProjectSettings.globalize_path(_MCP_BOOTSTRAP_SESSION_REL)
    if not FileAccess.file_exists(p):
        return ""
    var f := FileAccess.open(p, FileAccess.READ)
    if f == null:
        return ""
    var txt := f.get_as_text()
    f.close()
    var data: Variant = JSON.parse_string(txt)
    if typeof(data) != TYPE_DICTIONARY:
        return ""
    var d: Dictionary = data
    return str(d.get("session_id", "")).strip_edges()


func _write_runtime_gate_marker(payload: Dictionary) -> void:
    var ack := _read_bootstrap_session_id()
    if ack != "":
        payload = payload.duplicate()
        payload["bootstrap_session_ack"] = ack
    var tmp_global := ProjectSettings.globalize_path(_TMP_DIR_REL)
    DirAccess.make_dir_recursive_absolute(tmp_global)
    var marker_path := ProjectSettings.globalize_path(_RUNTIME_GATE_REL)
    var out := FileAccess.open(marker_path, FileAccess.WRITE)
    if out == null:
        return
    out.store_string(JSON.stringify(payload))
    out.close()
