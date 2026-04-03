# Migration Checklist

## Before migration

- Confirm old repository MCP entry is blocked.
- Confirm external repo is available locally.
- Confirm Python runtime is available.

## Migration steps

- Configure Cursor MCP to point to `pointer_gpf/mcp/server.py`.
- Run `install/install-mcp.ps1`.
- Install plugin into target project.
- Run `init_project_context`.
- Run `generate_flow_seed`.

## Verification

- `get_mcp_runtime_info` returns expected tool list.
- `check_plugin_status` is `ready`.
- `index.json` exists under `gameplayflow/project_context/`.
- Seed flow file exists under `gameplayflow/generated_flows/`.

## Rollback

- Restore previous MCP config in Cursor if needed.
- Use legacy bypass only for emergency maintenance.
