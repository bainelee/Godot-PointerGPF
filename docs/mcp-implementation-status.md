# PointerGPF MCP Implementation Status Matrix

This matrix records current implementation status based on repository evidence.

## Implemented

- Game-agnostic positioning is explicit: MCP contracts and runtime/report schemas are designed for cross-project Godot reuse rather than any single game.
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
- Runtime bootstrap responsibility is enforced in runtime path:
  - If engine is not open, MCP attempts target-project bootstrap and play-mode entry before step execution.
  - Failure payload includes `blocking_point`, `next_actions`, and `engine_bootstrap` evidence.
- Godot executable resolution priority is enforced:
  - project config `tools/game-test-runner/config/godot_executable.json`
  - tool arguments (`godot_executable` / `godot_editor_executable` / `godot_path`)
  - environment (`GODOT_EXE` / `GODOT_EDITOR_PATH` / `GODOT_PATH`)
  - no hardcoded local fallback path.
- Execution report includes runtime/input evidence fields:
  - `runtime_mode`
  - `runtime_entry`
  - `input_mode`
  - `os_input_interference`
  - `runtime_gate_passed`
  - `step_broadcast_summary.protocol_mode=three_phase`
  - `step_broadcast_summary.fail_fast_on_verify`
- Shell broadcast format is normalized for user-facing output:
  - Per-phase timestamp line: `[GPF-FLOW-TS] YYYY-MM-DD T HH:MM:SS` (local system time)
  - Per-phase semantic line: Chinese `开始执行` / `执行结果` / `验证结论`
  - User-facing output excludes technical field lines (`run=` / `phase=` / `id=` / `action=` / `bridge_ok=` / `verified=`).
- Test teardown rule is enforced in runtime path:
  - Every test run requests close action on success/failure/timeout/runtime gate failure.
  - `closeProject` semantics are fixed to stop `play_mode` and return editor idle state (editor process kept by default).
  - Close evidence is returned as `project_close` (`requested` / `acknowledged` / timeout/message).
- Runtime bridge mounting/runtime target resolution are hardened:
  - runtime bridge is mounted via autoload in target project plugin path.
  - node resolution is constrained to `current_scene` to avoid editor-tree false hits.
- Action-followed state verification is hardened:
  - generated follow-up verification uses short-window `wait + until.hint` polling to reduce same-frame false negatives.
- Temp-project safety gate is enforced:
  - temp directory project roots are rejected by default in runtime path.
  - temp-project engine autostart is blocked unless explicitly allowed for tests.
- Natural-language intent routing is available via `route_nl_intent` (basic flow aliases).
- Auto bug-fix loop is available via `auto_fix_game_bug` with `verification -> diagnosis -> patch -> retest` evidence.
- Basic flow dual conclusions are available in tool response and runtime artifact:
  - `tool_usability`
  - `gameplay_runnability`
  - `step_broadcast_summary`
- Adapter contract now exposes runtime requirements via `mcp/adapter_contract_v1.json` (`runtime_requirements`).
- Runtime bridge includes in-engine virtual input dispatch (`click`/`moveMouse`/`drag`) and virtual cursor overlay.

## Partially Implemented

- `exp_dir_rel` is configured and exposed in runtime info, but business-runtime read/write behavior requires dedicated artifact output and validation.
- Trend analysis currently outputs per-run JSON artifact; long-term historical aggregation is not yet automated inside repository CI.
- Runtime gate still depends on plugin-side marker evidence (`pointer_gpf/tmp/runtime_gate.json`) and bridge responsiveness; for unsupported adapters, close-request acknowledgment may timeout while request evidence remains available.

## Legacy restoration (tracked)

Repository work is restoring parity with the old archive MCP surface and runner contracts. Track these identifiers in audits and CI:

- `legacy_gameplayflow_tool_surface` — tool names and handler wiring for gameplay-flow style tools vs. `tools/game-test-runner/mcp/mcp_tool_surface_snapshot.py` / gap audit.
- `stepwise_chat_three_phase` — step broadcast / chat progress protocol aligned to `three_phase` execution reports (`step_broadcast_summary.protocol_mode`).
- `fix_loop_rounds_contract` — fix-loop round boundaries, artifacts, and handler expectations in `tools/game-test-runner/mcp/fix_loop_service.py` and related tests.

## Not Implemented (Before this execution)

- Legacy output path migration for `gameplayflow/*` and historical `gpf-exp` directories.
- Runtime default contract for `pointer_gpf/tmp` and `pointer_gpf/backups`.

## Accuracy Risks

- Nightly trend report exists but still relies on external consumer to build longitudinal dashboard and alerting policy.
