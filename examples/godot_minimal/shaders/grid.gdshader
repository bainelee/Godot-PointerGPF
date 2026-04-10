shader_type spatial;

// 网格密度（格子数量）
uniform float grid_scale : hint_range(1.0, 64.0) = 16.0;
// 网格线宽度
uniform float line_width : hint_range(0.001, 0.2) = 0.03;
// 网格线颜色（默认深灰）
uniform vec3 line_color : source_color = vec3(0.2, 0.2, 0.2);
// 底色（默认白色）
uniform vec3 base_color : source_color = vec3(1.0, 1.0, 1.0);

void fragment() {
	// 使用 UV 生成网格（PlaneMesh 默认 UV 为 0~1）
	vec2 grid = fract(UV * grid_scale);
	// 到最近网格线的距离
	vec2 edge = min(grid, 1.0 - grid);
	float line_mask = 1.0 - step(line_width, min(edge.x, edge.y));
	
	ALBEDO = mix(base_color, line_color, line_mask);
}
