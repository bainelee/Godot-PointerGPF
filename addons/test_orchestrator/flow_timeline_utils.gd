@tool
extends RefCounted


static func load_flow_step_entries(run_abs: String) -> Array:
	var timeline_path := run_abs.path_join("step_timeline.json")
	if FileAccess.file_exists(timeline_path):
		var timeline_text := FileAccess.get_file_as_string(timeline_path)
		var timeline_parsed: Variant = JSON.parse_string(timeline_text)
		if timeline_parsed is Dictionary:
			var steps_raw: Variant = (timeline_parsed as Dictionary).get("steps", [])
			if steps_raw is Array:
				var steps := steps_raw as Array
				var out: Array = []
				for step_raw in steps:
					if step_raw is Dictionary:
						out.append(step_raw)
				if not out.is_empty():
					return out
	var driver_flow_path := run_abs.path_join("logs").path_join("driver_flow.json")
	if FileAccess.file_exists(driver_flow_path):
		var flow_text := FileAccess.get_file_as_string(driver_flow_path)
		var flow_parsed: Variant = JSON.parse_string(flow_text)
		if flow_parsed is Dictionary:
			var steps_raw: Variant = (flow_parsed as Dictionary).get("steps", [])
			if steps_raw is Array:
				var converted: Array = []
				for step_raw in steps_raw:
					if not (step_raw is Dictionary):
						continue
					var step := step_raw as Dictionary
					var response_raw: Variant = step.get("response", {})
					var response: Dictionary = {}
					if response_raw is Dictionary:
						response = response_raw as Dictionary
					var evidence_files: Array = []
					var screenshot := ""
					if response.has("screenshot"):
						screenshot = str(response.get("screenshot", ""))
					if screenshot.begins_with("user://"):
						var base := screenshot.get_file()
						var rel := "screenshots/%s" % base
						if FileAccess.file_exists(run_abs.path_join(rel)):
							evidence_files.append(rel)
					converted.append(
						{
							"step_id": str(step.get("step_id", "")),
							"action": str(step.get("action", "")),
							"description": "driver step",
							"status": str(step.get("status", "unknown")),
							"duration_ms": int(step.get("duration_ms", 0)),
							"actual": "",
							"evidence_files": evidence_files,
						}
					)
				return converted
	return []


static func load_expected_flow_steps(flow_file_abs: String) -> Array:
	var out: Array = []
	if flow_file_abs.is_empty() or not FileAccess.file_exists(flow_file_abs):
		return out
	var text := FileAccess.get_file_as_string(flow_file_abs)
	var parsed: Variant = JSON.parse_string(text)
	if not (parsed is Dictionary):
		return out
	var root := parsed as Dictionary
	var steps_raw: Variant = root.get("steps", [])
	if not (steps_raw is Array):
		return out
	var idx := 1
	for step_raw in (steps_raw as Array):
		if not (step_raw is Dictionary):
			continue
		var step := step_raw as Dictionary
		var step_id := str(step.get("id", "")).strip_edges()
		if step_id.is_empty():
			step_id = "step_%02d" % idx
		out.append(step_id)
		idx += 1
	return out
