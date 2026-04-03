# Runtime Configuration

PointerGPF loads configuration in this order (later overrides earlier):

1. Repository default: `gtr.config.json`
2. Project override: `<project_root>/gtr.config.json`
3. Explicit override: `--config-file <path>`

## Supported keys

- `server_name`
- `server_version`
- `plugin_id`
- `plugin_cfg_rel`
- `plugin_template_dir_rel`
- `context_dir_rel`
- `index_rel`
- `seed_flow_dir_rel`
- `report_dir_rel`
- `exp_dir_rel`
- `scan_roots` (array)

`exp_dir_rel` is used for runtime artifacts such as `runtime/*.json` and `runtime/events.ndjson`.

## Example

```json
{
  "plugin_id": "my_project_plugin",
  "plugin_cfg_rel": "addons/my_project_plugin/plugin.cfg",
  "context_dir_rel": "pointer_gpf/project_context",
  "seed_flow_dir_rel": "pointer_gpf/generated_flows",
  "report_dir_rel": "pointer_gpf/reports",
  "exp_dir_rel": "pointer_gpf/gpf-exp",
  "scan_roots": ["scripts", "scenes", "data", "docs"]
}
```
