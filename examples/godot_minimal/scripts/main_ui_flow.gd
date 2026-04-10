extends CanvasLayer

@onready var start_screen: Control = $StartScreen
@onready var ui1: Control = $UI1
@onready var ui2_popup: Control = $UI2Popup
@onready var ui3: Control = $UI3


func _ready() -> void:
	_show_start_screen()


func _show_start_screen() -> void:
	start_screen.visible = true
	ui1.visible = false
	ui2_popup.visible = false
	ui3.visible = false


func _on_start_button_pressed() -> void:
	start_screen.visible = false
	ui1.visible = true
	ui2_popup.visible = false
	ui3.visible = false


func _on_ui1_open_ui2_button_pressed() -> void:
	ui2_popup.visible = true


func _on_ui2_next_button_pressed() -> void:
	ui2_popup.visible = false
	ui3.visible = true


func _on_ui3_close_button_pressed() -> void:
	ui3.visible = false
