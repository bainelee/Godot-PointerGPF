@tool
extends EditorPlugin


func _enter_tree() -> void:
    # Bridge-only plugin: runtime actions are controlled by MCP.
    pass


func _exit_tree() -> void:
    pass
