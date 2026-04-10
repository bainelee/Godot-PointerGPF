# Runtime Configuration

## 0) 入口与目录语义

- 默认 MCP 启动入口：`install/start-mcp.ps1` -> `mcp/server.py`
- legacy 子服务实现：`tools/game-test-runner/mcp/server.py`（历史兼容桥接，不作为默认入口）

`pointer_gpf` 在文档中可能指向仓库根、目标项目工作区目录、或 release 包根目录。详见：`docs/project-structure-baseline.md`。

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

## MCP tool arguments (common)

Most tools accept `project_root`. By default it must be a directory that contains `project.godot`. For rare tests or non-standard layouts only, you may pass `skip_godot_project_check=true`. Temporary-directory projects still require `allow_temp_project=true` where applicable.

## Version source recommendation

- 推荐将 `mcp/version_manifest.json` 作为版本事实源。
- `gtr.config.json` 与运行时默认常量可用于兼容和覆盖，但应通过校验流程保证一致性。

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
