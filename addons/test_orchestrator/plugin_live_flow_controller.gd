@tool
extends RefCounted


static func detect_live_run(runs_abs: String, live_flow_started_unix: float) -> Dictionary:
	var dir := DirAccess.open(runs_abs)
	if dir == null:
		return {}
	var best_run_id := ""
	var best_run_abs := ""
	dir.list_dir_begin()
	while true:
		var name := dir.get_next()
		if name == "":
			break
		if name.begins_with(".") or not dir.current_is_dir():
			continue
		var run_abs := runs_abs.path_join(name)
		var marker := run_abs.path_join("run_meta.json")
		var marker_mtime := 0.0
		if FileAccess.file_exists(marker):
			marker_mtime = float(FileAccess.get_modified_time(marker))
		if marker_mtime <= 0:
			var alt := run_abs.path_join("logs").path_join("driver_flow.json")
			if FileAccess.file_exists(alt):
				marker_mtime = float(FileAccess.get_modified_time(alt))
		if marker_mtime <= 0:
			continue
		if marker_mtime + 5.0 < live_flow_started_unix:
			continue
		if best_run_id.is_empty() or name > best_run_id:
			best_run_id = name
			best_run_abs = run_abs
	dir.list_dir_end()
	if best_run_id.is_empty():
		return {}
	return {
		"run_id": best_run_id,
		"run_abs": best_run_abs,
	}

