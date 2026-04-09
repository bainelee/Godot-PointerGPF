@tool
extends EditorPlugin

const _RuntimeBridge := preload("res://addons/pointer_gpf/runtime_bridge.gd")

var _runtime_bridge: Node


func _enter_tree() -> void:
    # Bridge-only plugin: runtime actions are controlled by MCP.
    _runtime_bridge = _RuntimeBridge.new()
    _runtime_bridge.name = "PointerGPFRuntimeBridge"
    get_tree().root.add_child(_runtime_bridge)


func _exit_tree() -> void:
    if is_instance_valid(_runtime_bridge):
        _runtime_bridge.queue_free()
    _runtime_bridge = null
