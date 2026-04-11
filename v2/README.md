# Pointer GPF V2

This directory contains the V2 rebuild scaffold for the Godot MCP.

Phase 1 scope is intentionally narrow, but it is no longer limited to schema-only flow validation:

- configure Godot executable
- sync plugin into a target Godot project
- run preflight checks
- run minimal and interactive flows through the file bridge
- support `click`, `wait`, `check`, and `closeProject`
- verify teardown after `closeProject`
- reject overlapping flows and manual multi-editor runs for one project

V2 does not include auto-fix, orchestration, NL routing, or Figma workflows.
