# Godot-PointerGPF

<p align="center">
  <img src="./pointer_gpf_logo.png" alt="PointerGPF cover" width="780" />
</p>

**Open-source MCP toolkit for Godot gray-box automation workflows.**  
Install and manage the Godot plugin, build project context, generate flow seeds, and run Figma-to-UI validation loops from one MCP server.

[简体中文](./README.zh-CN.md) | **English** | [Quick Start](./docs/quickstart.md) | [Changelog](./CHANGELOG.md)

---

## Why PointerGPF

Most automation setups for Godot are fragmented across scripts, ad-hoc notes, and editor actions. PointerGPF gives coding agents a stable MCP interface to:

- install/enable/update the plugin in target projects
- derive structured project context (`project_context/index.json`)
- generate first-pass flow seeds from real code/scene/data signals
- run gated Figma baseline comparison and fix suggestion loops

The result is a repeatable agent workflow that stays grounded in project files and explicit runtime artifacts.

## What's Included (v0.2.4.6)

- Plugin lifecycle tools: `install_godot_plugin`, `enable_godot_plugin`, `update_godot_plugin`, `check_plugin_status`
- Context pipeline: `init_project_context`, `refresh_project_context`, `generate_flow_seed`
- Figma validation loop: `figma_design_to_baseline`, `compare_figma_game_ui`, `annotate_ui_mismatch`, `approve_ui_fix_plan`, `suggest_ui_fix_patch`
- Contract + runtime diagnostics: `get_adapter_contract`, `get_mcp_runtime_info`
- Runtime outputs under `pointer_gpf/gpf-exp/runtime/` for traceability

## Supported MCP Clients

PointerGPF uses stdio MCP and works with clients that can launch a local command, including:

- Cursor
- Claude Code
- Codex CLI
- Windsurf / Gemini CLI (stdio-compatible mode)

## Quick Start

### 1) Give this to your coding agent

Tell the agent to read these files first:

- `docs/quickstart.md` (setup and update commands)
- `docs/configuration.md` (config options and output paths)

Then ask the agent to do these actions in order:

1. Run local check:
   ```powershell
   powershell -ExecutionPolicy Bypass -File "install/start-mcp.ps1"
   ```
2. Verify MCP runtime info:
   ```powershell
   python "mcp/server.py" --tool get_mcp_runtime_info --args "{}"
   ```
3. If you have a Godot project, run plugin install:
   ```powershell
   python "mcp/server.py" --tool install_godot_plugin --project-root "D:/path/to/your/godot/project"
   ```

### 2) You must do this manually (human-only)

These steps require your own click/confirmation in the IDE:

1. Open Cursor MCP settings and add/edit server config.
2. Paste config:

   ```json
   {
     "mcpServers": {
       "pointer-gpf": {
         "command": "C:/Users/your-user/AppData/Local/Programs/Python/Python311/python.exe",
         "args": [
           "-u",
           "D:/AI/pointer_gpf/mcp/server.py",
           "--stdio"
         ]
       }
     }
   }
   ```

3. Turn on the server switch in MCP panel.
4. Confirm status dot is green and tools are visible.

If the status dot is red, restart Cursor and run `install/start-mcp.ps1` again.

## Updating

Use this command-style update flow:

```powershell
.\pointer-gpf.cmd update
```

Check updates only:

```powershell
.\pointer-gpf.cmd check
```

Notes:

- `update` uses remote release by default.
- `-ForceRemote` now has highest priority and always resolves GitHub release assets first.
- Default update scope now syncs `mcp/`, `gtr.config.json`, and `godot_plugin_template/` together to avoid version drift.
- Successful update logs now report installed versions (`installed_manifest_version`, `installed_runtime_version`) instead of only pre-update manifest targets.
- To update from a local package directory:

```powershell
powershell -ExecutionPolicy Bypass -File "install/pointer-gpf.ps1" update -PackageDir "D:/path/to/pointer_gpf_package"
```

## Core Workflows

### 1) Plugin setup for a target Godot project

**Give this to your coding agent:**

```powershell
python "mcp/server.py" --tool install_godot_plugin --project-root "D:/path/to/your/godot/project"
```

**You must do this manually (human-only):**

- Open Godot editor and verify plugin is enabled in Project Settings.
- Confirm `addons/pointer_gpf` exists in the target project.

### 2) Build project context + flow seed

**Give this to your coding agent:**

```powershell
python "mcp/server.py" --tool init_project_context --project-root "D:/path/to/your/godot/project" --max-files 2500
python "mcp/server.py" --tool generate_flow_seed --project-root "D:/path/to/your/godot/project" --flow-id "smoke_seed" --strategy "auto"
```

**You must do this manually (human-only):**

- Review generated files under `pointer_gpf/project_context/`.
- Check whether generated flow seed matches your project intent before running real tests.

### 3) Figma-to-game UI compare loop

**Give this to your coding agent:**

`figma_design_to_baseline -> compare_figma_game_ui -> annotate_ui_mismatch -> approve_ui_fix_plan -> suggest_ui_fix_patch`

**You must do this manually (human-only):**

- Decide whether to approve UI fix plan (human approval gate).
- Verify screenshot/baseline inputs are the correct design version before approval.

## Documentation

- Quick start: [`docs/quickstart.md`](./docs/quickstart.md)
- Configuration: [`docs/configuration.md`](./docs/configuration.md)
- Adapter contract: [`docs/godot-adapter-contract-v1.md`](./docs/godot-adapter-contract-v1.md)
- Adoption guides: [`docs/adoption-overview.md`](./docs/adoption-overview.md), [`docs/migration-checklist.md`](./docs/migration-checklist.md)
- Testing spec: [`docs/mcp-testing-spec.md`](./docs/mcp-testing-spec.md)

## Development & CI

- **Version source of truth:** the repo root `VERSION` file (four-part `major.minor.patch.build`). Release automation reads it; use `scripts/sync-version.ps1` (invoked by `scripts/release.ps1`) to propagate it to tracked files—avoid editing version strings in multiple places by hand.
- **One-click release (maintainers):** from the repo root, run `scripts/release.ps1`. Use `-DryRun` to print the planned steps without writing files or calling git/GitHub. A normal run syncs versions, builds the zip (same layout as CI), updates `mcp/version_manifest.json`, commits, and pushes a **`v*`** tag. **GitHub Release is created by CI** (`.github/workflows/release-package.yml` on tag push), not by local `gh release create`, to avoid racing the workflow.
- **Release workflow:** `.github/workflows/release-package.yml` is **tag-driven** on push of tags matching **`v*`**. **`workflow_dispatch`** is optional for manual reruns (you can pass a `version` input, or run the workflow from a tag ref).
- **CI layers:** **`mcp-smoke.yml`** runs on `main` pushes/PRs for fast feedback (short timeout). **`mcp-integration.yml`** runs on a **nightly** schedule and via **`workflow_dispatch`**, with scope **`quick`** (small sample) vs **`full`** (repo-scale checks, Figma pipeline, trend report artifact).
- Workflows:
  - `.github/workflows/mcp-smoke.yml`
  - `.github/workflows/mcp-integration.yml`
  - `.github/workflows/release-package.yml`
- Validation scripts:
  - `scripts/assert-mcp-artifacts.ps1`
  - `scripts/verify-cross-project.ps1`
  - `scripts/update-version-manifest.ps1`
  - `scripts/release.ps1`

## License

See [`LICENSE`](./LICENSE).
