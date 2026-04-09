@tool
extends RefCounted


static func read_run_status(run_abs: String) -> String:
	var report_path := run_abs.path_join("report.json")
	if not FileAccess.file_exists(report_path):
		return "unknown"
	var text := FileAccess.get_file_as_string(report_path)
	var parsed: Variant = JSON.parse_string(text)
	if parsed is Dictionary:
		return str((parsed as Dictionary).get("status", "unknown"))
	return "unknown"


static func build_failure_summary_text(run_abs: String) -> String:
	var summary_path := run_abs.path_join("failure_summary.json")
	if not FileAccess.file_exists(summary_path):
		return "Latest failure: failure_summary.json missing"
	var text := FileAccess.get_file_as_string(summary_path)
	var parsed: Variant = JSON.parse_string(text)
	if not (parsed is Dictionary):
		return "Latest failure: failure_summary.json parse failed"
	var summary := parsed as Dictionary
	var primary: Dictionary = {}
	var primary_raw: Variant = summary.get("primary_failure", {})
	if primary_raw is Dictionary:
		primary = primary_raw as Dictionary
	var step := str(primary.get("step", ""))
	if step.is_empty():
		step = str(primary.get("step_id", ""))
	var category := str(primary.get("category", ""))
	var actual := str(primary.get("actual", ""))
	if actual.length() > 120:
		actual = actual.substr(0, 117) + "..."
	if step.is_empty() and category.is_empty() and actual.is_empty():
		var status := str(summary.get("status", "unknown"))
		return "Latest failure: none (status=%s)" % status
	return "Latest failure: step=%s | category=%s | actual=%s" % [step, category, actual]

