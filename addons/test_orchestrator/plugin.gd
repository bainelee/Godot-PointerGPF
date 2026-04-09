@tool
extends EditorPlugin

var _dock: VBoxContainer


func _enter_tree() -> void:
	_dock = VBoxContainer.new()
	_dock.name = "Test Orchestrator"

	var title := Label.new()
	title.text = "Test Orchestrator (Bridge Mode)"
	_dock.add_child(title)

	var desc := Label.new()
	desc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	desc.text = "Gameplay flow controls are intentionally disabled in Godot. Use MCP tools from your IDE (Cursor) for run/start/pull/report actions."
	_dock.add_child(desc)

	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)


func _exit_tree() -> void:
	if _dock != null:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null
