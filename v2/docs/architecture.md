# Pointer GPF V2 Architecture

## Phase 1

V2 phase 1 is intentionally narrow.

Core responsibilities:

- configure Godot executable
- sync plugin to a target Godot project
- run preflight checks
- validate a minimal flow contract

Not in scope:

- auto-fix
- repair loops
- NL routing
- Figma comparison
- UI patch generation

## Design rule

If a problem can be classified before flow execution, it belongs in preflight.

Examples:

- Godot executable missing
- plugin files missing
- runtime tmp not writable
- scene ext_resource UID mismatch

