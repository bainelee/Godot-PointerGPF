# PointerGPF MCP Implementation Status Matrix

This matrix records current implementation status based on repository evidence.

## Implemented

- stdio + CLI dual entry: `mcp/server.py` (`_run_stdio_mcp`, `_run_cli_mode`, `main` routing).
- MCP tool schema + handler reuse: `mcp/server.py` (`_build_tool_specs`, `_build_tool_map`, `tools/list`, `tools/call`).
- Figma collaboration pipeline tools:
  - `figma_design_to_baseline`
  - `compare_figma_game_ui`
  - `annotate_ui_mismatch`
  - `approve_ui_fix_plan`
  - `suggest_ui_fix_patch`
- Approval gate is enforced for fix suggestion generation (`approved=true` required).
- Workspace consolidation (core paths): `pointer_gpf/project_context`, `pointer_gpf/generated_flows`, `pointer_gpf/reports`.
- Version sync: `mcp/server.py` (`DEFAULT_SERVER_VERSION`), `godot_plugin_template/addons/pointer_gpf/plugin.cfg`, `mcp/version_manifest.json`.
- CI split: `.github/workflows/mcp-smoke.yml` (PR/push smoke) and `.github/workflows/mcp-integration.yml` (scheduled/manual integration).
- Smoke protocol assertions include stdio `tools/call` positive + negative path checks.
- Artifact contract assertions are automated via `scripts/assert-mcp-artifacts.ps1` and wired in smoke/integration workflows.
- Integration workflow produces trend report artifact (`mcp_integration_trend_report.json`).

## Partially Implemented

- `exp_dir_rel` is configured and exposed in runtime info, but business-runtime read/write behavior requires dedicated artifact output and validation.
- Trend analysis currently outputs per-run JSON artifact; long-term historical aggregation is not yet automated inside repository CI.
- Godot plugin side remains bridge-only template; Figma-vs-game compare executes at MCP layer using supplied screenshots/metadata.

## Not Implemented (Before this execution)

- Legacy output path migration for `gameplayflow/*` and historical `gpf-exp` directories.
- Runtime default contract for `pointer_gpf/tmp` and `pointer_gpf/backups`.

## Accuracy Risks

- Nightly trend report exists but still relies on external consumer to build longitudinal dashboard and alerting policy.
