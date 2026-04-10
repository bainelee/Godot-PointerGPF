extends Node3D

## 可复用的测试敌人：使用 Sprite3D 纸片风格，显示 triangle_inverted_red.png
## 始终面向玩家，被子弹击中时显示红圈特效（支持多受击点，各自 2 秒后消失）
## 受击范围由纹理透明通道控制：仅在不透明区域（alpha > 阈值）受击

const MAX_HITS := 16
const HIT_FADE_SEC := 2.0

## 启用时：仅在纹理不透明区域（alpha > 阈值）受击
@export var use_texture_alpha_for_hit: bool = true
## 纹理 alpha 低于此值视为透明，不触发受击（抗锯齿边缘可适当调高，如 0.3）
@export var hit_alpha_threshold: float = 0.2
## 敌人参考高度（世界单位），与 ground_clearance_ratio 配合计算离地距离
@export var float_height: float = 1.0
## 离地比例：高度 100 时离地 20 即 0.2
@export var ground_clearance_ratio: float = 0.2
## 上下浮动幅度（世界单位）
@export var float_bob_amplitude: float = 0.04
## 浮动周期（秒），完成一次上下循环所需时间
@export var float_bob_period: float = 2.0

var _player: Node3D
var _sprite: Sprite3D
var _hit_material: ShaderMaterial
var _hits: Array[Dictionary] = []  # [{uv: Vector2, time: float}, ...]
var _texture_image: Image = null  # 缓存纹理的 Image，用于 alpha 采样
var _sprite_height: float = 1.0  # 由纹理实际尺寸计算，用于悬浮定位


func _ready() -> void:
	_sprite = get_node_or_null("Sprite3D")
	if _sprite:
		_setup_hit_material()
		# 从纹理计算 Sprite3D 实际高度，用于正确悬浮
		var tex = _sprite.texture
		if tex:
			_sprite_height = tex.get_height() * _sprite.pixel_size
		else:
			_sprite_height = float_height
	_apply_float_position()
	
	# 击中由玩家准星射线判定，HitArea.area_entered 不再使用
	
	_player = get_tree().get_first_node_in_group("player")
	if not _player:
		call_deferred("_find_player")


func _is_opaque_at_uv(uv: Vector2) -> bool:
	if not use_texture_alpha_for_hit or not _texture_image:
		return true
	var w := _texture_image.get_width()
	var h := _texture_image.get_height()
	if w <= 0 or h <= 0:
		return true
	var px := clampi(int(uv.x * w), 0, w - 1)
	var py := clampi(int(uv.y * h), 0, h - 1)
	return _texture_image.get_pixel(px, py).a >= hit_alpha_threshold


func _setup_hit_material() -> void:
	if not _sprite:
		return
	if use_texture_alpha_for_hit and _sprite.texture:
		_texture_image = _sprite.texture.get_image()
		if _texture_image:
			if _texture_image.is_compressed():
				_texture_image.decompress()
		elif _sprite.texture.resource_path:
			# 压缩纹理可能无法 get_image，尝试从源文件加载
			_texture_image = Image.load_from_file(_sprite.texture.resource_path)
	var base_mat = load("res://shaders/sprite3d_hit_material.tres") as ShaderMaterial
	if base_mat:
		_hit_material = base_mat.duplicate() as ShaderMaterial
		_hit_material.set_shader_parameter("texture_albedo", _sprite.texture)
		_hit_material.set_shader_parameter("hit_count", 0)
		var empty_uvs := PackedVector2Array()
		var empty_times := PackedFloat32Array()
		for i in MAX_HITS:
			empty_uvs.append(Vector2(-10.0, -10.0))
			empty_times.append(-1000.0)
		_hit_material.set_shader_parameter("hit_uvs", empty_uvs)
		_hit_material.set_shader_parameter("hit_times", empty_times)
		_sprite.material_override = _hit_material


## 射线与精灵平面相交检测，仅依据纹理透明通道判定受击（无 3D 碰撞）
## 返回 {hit: bool, position: Vector3, distance: float}，hit 为 true 表示命中不透明区域
func ray_intersect_sprite(origin: Vector3, direction: Vector3) -> Dictionary:
	if not _sprite or not _sprite.texture or not _hit_material:
		return {"hit": false, "position": Vector3.ZERO, "distance": INF}
	var plane_origin := _sprite.global_position
	var to_cam := origin - plane_origin
	if to_cam.length_squared() < 0.0001:
		return {"hit": false, "position": Vector3.ZERO, "distance": INF}
	var plane_normal := to_cam.normalized()
	var denom := plane_normal.dot(direction)
	if absf(denom) < 0.0001:
		return {"hit": false, "position": Vector3.ZERO, "distance": INF}
	var t := (plane_origin - origin).dot(plane_normal) / denom
	if t < 0.0:
		return {"hit": false, "position": Vector3.ZERO, "distance": INF}
	var hit_world := origin + direction * t
	var local := _sprite.to_local(hit_world)
	var tex := _sprite.texture
	var w := tex.get_width() * _sprite.pixel_size
	var h := tex.get_height() * _sprite.pixel_size
	if absf(local.x) > w * 0.5 or absf(local.y) > h * 0.5:
		return {"hit": false, "position": hit_world, "distance": t}
	var uv := Vector2(local.x / w + 0.5, 0.5 - local.y / h).clamp(Vector2.ZERO, Vector2.ONE)
	if not _is_opaque_at_uv(uv):
		return {"hit": false, "position": hit_world, "distance": t}
	return {"hit": true, "position": hit_world, "distance": t}


func _on_bullet_hit(hit_position: Vector3) -> bool:
	if not _hit_material or not _sprite:
		return false
	return _apply_hit_effect(hit_position)


func _apply_hit_effect(hit_position: Vector3) -> bool:
	var local = _sprite.to_local(hit_position)
	var tex = _sprite.texture
	var w = tex.get_width() * _sprite.pixel_size if tex else 1.0
	var h = tex.get_height() * _sprite.pixel_size if tex else 1.0
	var uv = Vector2(local.x / w + 0.5, 0.5 - local.y / h)
	uv = uv.clamp(Vector2.ZERO, Vector2.ONE)
	# 纹理透明通道：仅在非透明像素处受击
	if not _is_opaque_at_uv(uv):
		return false
	var now := Time.get_ticks_msec() / 1000.0
	# 移除已超过 2 秒的旧受击点
	_hits = _hits.filter(func(h): return now - h.time < HIT_FADE_SEC)
	if _hits.size() >= MAX_HITS:
		_hits.pop_front()  # 满时移除最旧的
	_hits.append({"uv": uv, "time": now})
	_sync_hits_to_shader()
	return true


func _sync_hits_to_shader() -> void:
	var now := Time.get_ticks_msec() / 1000.0
	_hits = _hits.filter(func(h): return now - h.time < HIT_FADE_SEC)
	var uvs: PackedVector2Array = []
	var times: PackedFloat32Array = []
	for h in _hits:
		uvs.append(h.uv)
		times.append(h.time)
	# Shader 需要固定 16 个元素，用无效值填充
	while uvs.size() < MAX_HITS:
		uvs.append(Vector2(-10.0, -10.0))
		times.append(-1000.0)
	_hit_material.set_shader_parameter("hit_uvs", uvs)
	_hit_material.set_shader_parameter("hit_times", times)
	_hit_material.set_shader_parameter("hit_count", _hits.size())


func _find_player() -> void:
	_player = get_tree().get_first_node_in_group("player")


func _apply_float_position() -> void:
	# 离地 = 视觉高度 × 比例；视觉高度 = 纹理高度 × 节点 scale
	var s := scale.y  # 使用 Y 轴 scale 参与悬浮计算
	var visual_height := _sprite_height * s
	var clearance := visual_height * ground_clearance_ratio
	var sprite_bottom_in_local := 0.5 - _sprite_height * 0.5
	var base_y := clearance - sprite_bottom_in_local * s
	var t := Time.get_ticks_msec() / 1000.0
	var bob := sin(t * TAU / float_bob_period) * float_bob_amplitude
	position.y = base_y + bob


func _process(delta: float) -> void:
	# 定期同步受击点到 shader，移除已过期的
	if _hits.size() > 0:
		_sync_hits_to_shader()
	# 悬浮与上下浮动
	_apply_float_position()
	# 始终面向玩家（绕 Y 轴旋转）
	if _player:
		var dir := _player.global_position - global_position
		dir.y = 0
		if dir.length_squared() > 0.001:
			rotation.y = atan2(-dir.x, -dir.z)
