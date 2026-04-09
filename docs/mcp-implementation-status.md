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
- Runtime gate contract path is available in `run_game_basic_test_flow` (`require_play_mode`) with structured `RUNTIME_GATE_FAILED`.
- Execution report includes runtime/input evidence fields:
  - `runtime_mode`
  - `runtime_entry`
  - `input_mode`
  - `os_input_interference`
  - `runtime_gate_passed`
  - `step_broadcast_summary.protocol_mode=three_phase`
  - `step_broadcast_summary.fail_fast_on_verify`
- Adapter contract now exposes runtime requirements via `mcp/adapter_contract_v1.json` (`runtime_requirements`).
- Runtime bridge includes in-engine virtual input dispatch (`click`/`moveMouse`/`drag`) and virtual cursor overlay.

## Partially Implemented

- `exp_dir_rel` is configured and exposed in runtime info, but business-runtime read/write behavior requires dedicated artifact output and validation.
- Trend analysis currently outputs per-run JSON artifact; long-term historical aggregation is not yet automated inside repository CI.
- Runtime gate currently relies on runtime marker evidence (`pointer_gpf/tmp/runtime_gate.json`) for deterministic automation; automatic F5-equivalent launch is not fully implemented.

## Not Implemented (Before this execution)

- Legacy output path migration for `gameplayflow/*` and historical `gpf-exp` directories.
- Runtime default contract for `pointer_gpf/tmp` and `pointer_gpf/backups`.

## Accuracy Risks

- Nightly trend report exists but still relies on external consumer to build longitudinal dashboard and alerting policy.
