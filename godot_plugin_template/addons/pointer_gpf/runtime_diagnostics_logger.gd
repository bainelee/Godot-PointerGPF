extends Logger
## Forwards Engine._log_error (GDScript errors, parse errors, etc.) to RuntimeDiagnosticsWriter via a thread-safe queue.

var _writer: RefCounted


func _init(writer: RefCounted) -> void:
    _writer = writer


func _log_message(_message: String, _error: bool) -> void:
    pass


func _log_error(
    _function: String,
    file: String,
    line: int,
    _code: String,
    rationale: String,
    _editor_notify: bool,
    _error_type: int,
    script_backtraces: Array,
) -> void:
    if _writer == null or not _writer.has_method("enqueue_engine_error"):
        return
    var stack_text := ""
    for st in script_backtraces:
        stack_text += str(st) + "\n"
    _writer.enqueue_engine_error(rationale, file, line, stack_text.strip_edges())
