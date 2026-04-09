@tool
extends EditorPlugin

const _RuntimeBridge := preload("res://addons/pointer_gpf/runtime_bridge.gd")

var _bridge: Node


func _enter_tree() -> void:
    # Bridge-only plugin: runtime actions are controlled by MCP.
    _bridge = _RuntimeBridge.new()
    _bridge.name = "PointerGPFRuntimeBridge"
    add_child(_bridge)


func _exit_tree() -> void:
    if is_instance_valid(_bridge):
        _bridge.queue_free()
    _bridge = null
