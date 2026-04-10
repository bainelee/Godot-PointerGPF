extends SceneTree

func _initialize() -> void:
	var packed: PackedScene = load("res://scenes/main_scene_example.tscn")
	var scene := packed.instantiate()
	get_root().add_child(scene)
	call_deferred("_capture_after_render")


func _capture_after_render() -> void:
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var viewport_texture := get_root().get_texture()
	if viewport_texture == null:
		quit(1)
		return
	var image := viewport_texture.get_image()
	if image == null:
		quit(1)
		return
	image.save_png("res://assets/game_capture.png")
	quit()
