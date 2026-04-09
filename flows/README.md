# Flow Assets Scope

`flows/` stores reusable flow assets for MCP runner validation.

## Game-Agnostic Rule

- Default MCP capabilities must remain game-agnostic and reusable across different Godot projects.
- Flow files are test assets, not product-level game design assumptions.

## Legacy Fixtures

- Some files under `flows/suites/regression/gameplay/` are kept for historical compatibility replay.
- Their step ids and names should be treated as opaque fixture identifiers, not required domain language for new projects.
- New flows should prefer neutral naming and generic assertions.

