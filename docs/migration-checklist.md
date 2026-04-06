# Migration Checklist

## Before migration

- Confirm old repository MCP entry is blocked.
- Confirm external repo is available locally.
- Confirm Python runtime is available.

## Migration steps

- Configure Cursor MCP to point to `mcp/server.py` in this repository (or an absolute path like `D:/AI/pointer_gpf/mcp/server.py`).
- Run `install/install-mcp.ps1`.
- Install plugin into target project.
- Run `init_project_context`.
- Run `generate_flow_seed`.

If legacy output paths exist (`gameplayflow/*` or project-root `gpf-exp`), run:

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/migrate-legacy-layout.ps1" -ProjectRoot "D:/path/to/your/godot/project" -DryRun
```

Then execute without `-DryRun` to apply migration.

## Verification

- `get_mcp_runtime_info` returns expected tool list.
- `check_plugin_status` is `ready`.
- `index.json` exists under `pointer_gpf/project_context/`.
- Seed flow file exists under `pointer_gpf/generated_flows/`.
- Runtime artifacts exist under `pointer_gpf/gpf-exp/runtime/`.

可使用自动化断言脚本替代手动核对：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/assert-mcp-artifacts.ps1" `
  -ProjectRoot "D:/path/to/your/godot/project" `
  -FlowId "smoke_seed"
```

## Rollback

- Restore previous MCP config in Cursor if needed.
- Use legacy bypass only for emergency maintenance.
