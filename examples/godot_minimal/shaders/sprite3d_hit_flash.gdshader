shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_opaque, depth_prepass_alpha;

// 纹理（脚本中从 Sprite3D 传入）
uniform sampler2D texture_albedo : source_color;

// 多受击点数组（最多 16 个）
uniform vec2 hit_uvs[16];
uniform float hit_times[16];
uniform int hit_count = 0;
// 红圈半径（UV 空间）
uniform float hit_radius : hint_range(0.005, 0.2) = 0.027;
// 红圈颜色
uniform vec4 hit_color : source_color = vec4(1.0, 0.0, 0.0, 1.0);

void fragment() {
	vec4 tex_col = texture(texture_albedo, UV);
	float total_circle_alpha = 0.0;
	
	// 遍历所有受击点，累加红圈（2 秒后自动淡出）
	for (int i = 0; i < 16; i++) {
		if (i >= hit_count) break;
		
		vec2 huv = hit_uvs[i];
		float htime = hit_times[i];
		if (htime < 0.0 || huv.x < 0.0 || huv.x > 1.0 || huv.y < 0.0 || huv.y > 1.0) continue;
		
		float elapsed = TIME - htime;
		float fade = 1.0 - clamp(elapsed / 2.0, 0.0, 1.0);
		if (fade <= 0.001) continue;
		
		float dist = distance(UV, huv);
		float in_circle = 1.0 - smoothstep(hit_radius * 0.8, hit_radius, dist);
		total_circle_alpha = max(total_circle_alpha, in_circle * fade * hit_color.a);
	}
	
	total_circle_alpha = clamp(total_circle_alpha, 0.0, 1.0);
	vec4 final_col = mix(tex_col, hit_color, total_circle_alpha);
	
	ALBEDO = final_col.rgb;
	ALPHA = final_col.a;
}
