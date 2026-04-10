extends Area3D

## 基础子弹：纯视觉，飞向准星射线确定的命中点
## 命中逻辑由玩家发射时射线检测完成

@export var speed: float = 80.0
@export var max_lifetime: float = 3.0
const MAX_FLY_DISTANCE := 5000.0

var _direction: Vector3 = Vector3.FORWARD
var _target_position: Vector3
var _lifetime: float = 0.0


func setup(direction: Vector3, start_position: Vector3, target_position: Vector3) -> void:
	_direction = direction.normalized()
	global_position = start_position
	_target_position = target_position
	look_at(global_position + _direction)
	# 根据速度计算飞完 5000 所需时间，到时自动销毁
	var fly_time := MAX_FLY_DISTANCE / speed
	var timer := get_tree().create_timer(fly_time)
	timer.timeout.connect(_on_max_distance_timeout)


func _physics_process(delta: float) -> void:
	var to_target := _target_position - global_position
	var dist := to_target.length()
	
	if dist <= 0.05:
		queue_free()
		return
	
	var move := to_target.normalized() * minf(speed * delta, dist)
	global_position += move
	
	_lifetime += delta
	if _lifetime >= max_lifetime:
		queue_free()
		return


func _on_max_distance_timeout() -> void:
	if is_instance_valid(self):
		queue_free()


func _on_body_entered(body: Node3D) -> void:
	# 忽略与玩家自身的碰撞
	if body is CharacterBody3D and body.is_in_group("player"):
		return
	queue_free()


func _on_area_entered(_area: Area3D) -> void:
	queue_free()
