@tool
extends RefCounted


static func build_step_detail_text(step: Dictionary) -> String:
	var step_id := str(step.get("step_id", ""))
	var action := str(step.get("action", ""))
	var status := str(step.get("status", "unknown"))
	var desc := str(step.get("description", ""))
	var expected := str(step.get("expected", ""))
	var actual := str(step.get("actual", ""))
	return (
		"Step detail:\n"
		+ "- id: %s\n" % step_id
		+ "- status: %s\n" % status
		+ "- action: %s\n" % action
		+ "- validation: %s\n" % desc
		+ "- expected: %s\n" % expected
		+ "- actual: %s" % actual
	)

