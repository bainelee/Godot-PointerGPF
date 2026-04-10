extends Control

## 屏幕中心准星

@export var color: Color = Color(1.0, 1.0, 1.0, 0.9)
@export var length: float = 12.0
@export var thickness: float = 2.0
@export var gap: float = 4.0  # 中心留空，避免遮挡


func _draw() -> void:
	var center := size / 2
	# 上下左右四条线
	draw_rect(Rect2(center.x - thickness / 2, center.y - length - gap, thickness, length), color)   # 上
	draw_rect(Rect2(center.x - thickness / 2, center.y + gap, thickness, length), color)           # 下
	draw_rect(Rect2(center.x - length - gap, center.y - thickness / 2, length, thickness), color) # 左
	draw_rect(Rect2(center.x + gap, center.y - thickness / 2, length, thickness), color)           # 右
