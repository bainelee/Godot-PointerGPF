extends CanvasLayer

@onready var _mode_button: Button = %ModeButton

func _ready() -> void:
	_mode_button.pressed.connect(_on_mode_button_pressed)
	call_deferred("_connect_player")


func _connect_player() -> void:
	var player := get_tree().get_first_node_in_group("player")
	if player == null:
		return
	if player.has_signal("pointer_ui_mode_changed"):
		if not player.pointer_ui_mode_changed.is_connected(_on_player_pointer_mode_changed):
			player.pointer_ui_mode_changed.connect(_on_player_pointer_mode_changed)
	_on_player_pointer_mode_changed(player.pointer_ui_mode)


func _on_mode_button_pressed() -> void:
	var player := get_tree().get_first_node_in_group("player")
	if player and player.has_method("toggle_pointer_ui_mode"):
		player.toggle_pointer_ui_mode()


func _on_player_pointer_mode_changed(active: bool) -> void:
	if active:
		_mode_button.text = "返回游戏视角"
	else:
		_mode_button.text = "指针模式 (Alt)"
