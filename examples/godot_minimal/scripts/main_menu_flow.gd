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
	_connect_ui_signals()


func _connect_ui_signals() -> void:
	# 子场景实例上的信号在 .tscn 里易丢失；在代码里连接更稳
	var start_btn := start_screen.get_node_or_null("StartButton") as Button
	if start_btn and not start_btn.pressed.is_connected(_on_start_button_pressed):
		start_btn.pressed.connect(_on_start_button_pressed)

	var open_ui2 := ui1.get_node_or_null("OpenUI2Button") as Button
	if open_ui2 and not open_ui2.pressed.is_connected(_on_ui1_open_ui2_button_pressed):
		open_ui2.pressed.connect(_on_ui1_open_ui2_button_pressed)

	var next_btn := ui2_popup.get_node_or_null("NextButton") as Button
	if next_btn and not next_btn.pressed.is_connected(_on_ui2_next_button_pressed):
		next_btn.pressed.connect(_on_ui2_next_button_pressed)

	var close_btn := ui3.get_node_or_null("CloseButton") as Button
	if close_btn and not close_btn.pressed.is_connected(_on_ui3_close_button_pressed):
		close_btn.pressed.connect(_on_ui3_close_button_pressed)


func _on_start_button_pressed() -> void:
	var err := get_tree().change_scene_to_file(GAME_LEVEL)
	if err != OK:
		push_error("main_menu_flow: 无法切换到 %s，错误码 %s" % [GAME_LEVEL, err])


func _on_ui1_open_ui2_button_pressed() -> void:
	ui2_popup.visible = true


func _on_ui2_next_button_pressed() -> void:
	ui2_popup.visible = false
	ui3.visible = true


func _on_ui3_close_button_pressed() -> void:
	ui3.visible = false
