# PointerGPF MCP Implementation Status Matrix

This matrix records current implementation status based on repository evidence.

## Implemented

- stdio + CLI dual entry: `mcp/server.py` (`_run_stdio_mcp`, `_run_cli_mode`, `main` routing).
- MCP tool schema + handler reuse: `mcp/server.py` (`_build_tool_specs`, `_build_tool_map`, `tools/list`, `tools/call`).
- Workspace consolidation (core paths): `pointer_gpf/project_context`, `pointer_gpf/generated_flows`, `pointer_gpf/reports`.
- Version sync: `mcp/server.py` (`DEFAULT_SERVER_VERSION`), `godot_plugin_template/addons/pointer_gpf/plugin.cfg`, `mcp/version_manifest.json`.
- CI split: `.github/workflows/mcp-smoke.yml` (PR/push smoke) and `.github/workflows/mcp-integration.yml` (scheduled/manual integration).

## Partially Implemented

- `exp_dir_rel` is configured and exposed in runtime info, but business-runtime read/write behavior requires dedicated artifact output and validation.
- Smoke budget wording: currently enforced as job timeout + per-step threshold; wording should avoid claiming hard per-step 120s for all steps.

## Not Implemented (Before this execution)

- Legacy output path migration for `gameplayflow/*` and historical `gpf-exp` directories.
- Runtime default contract for `pointer_gpf/tmp` and `pointer_gpf/backups`.

## Accuracy Risks

- `docs/migration-checklist.md` uses `pointer_gpf/mcp/server.py` wording that can be confused with a repository subfolder path.
- `README.md` CI section does not fully describe stdio protocol smoke and integration workflow positioning.
