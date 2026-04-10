extends CanvasLayer

const GAME_LEVEL := "res://scenes/game_level.tscn"

@onready var dashboard: Control = $Dashboard
@onready var start_screen: Control = $StartScreen
@onready var ui1: Control = $UI1
@onready var ui2_popup: Control = $UI2Popup
@onready var ui3: Control = $UI3


func _ready() -> void:
	dashboard.visible = false
	ui1.visible = false
	ui2_popup.visible = false
	ui3.visible = false
	start_screen.visible = true


func _on_start_button_pressed() -> void:
	get_tree().change_scene_to_file(GAME_LEVEL)


func _on_ui1_open_ui2_button_pressed() -> void:
	ui2_popup.visible = true


func _on_ui2_next_button_pressed() -> void:
	ui2_popup.visible = false
	ui3.visible = true


func _on_ui3_close_button_pressed() -> void:
	ui3.visible = false
