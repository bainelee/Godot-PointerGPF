extends Node3D

## 主场景启动时加载第一人称控制器和准星

const POINTER_HUD := preload("res://scenes/ui/game_pointer_hud.tscn")


func _ready() -> void:
	var fps_scene = load("res://scenes/player/fps_controller.tscn") as PackedScene
	if fps_scene:
		var fps = fps_scene.instantiate()
		fps.position = Vector3(0, 2, 5)
		add_child(fps)

	var crosshair_scene = load("res://scenes/ui/crosshair.tscn") as PackedScene
	if crosshair_scene:
		add_child(crosshair_scene.instantiate())

	add_child(POINTER_HUD.instantiate())
