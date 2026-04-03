# PointerGPF Adoption Overview

## Recommended path

1. Clone PointerGPF repository.
2. Configure MCP in Cursor (`mcp/server.py`).
3. Install plugin into target Godot project.
4. Initialize project context.
5. Generate seed flow and refine.

## Core commands

- `install_godot_plugin`
- `check_plugin_status`
- `init_project_context`
- `refresh_project_context`
- `generate_flow_seed`
- `get_adapter_contract`

## Output artifacts

- `gameplayflow/project_context/*.md`
- `gameplayflow/project_context/index.json`
- `gameplayflow/generated_flows/*.json`

## Safety model

- Legacy embedded MCP entry in old repository remains blocked by default.
- Operational entry should always be external package MCP.
