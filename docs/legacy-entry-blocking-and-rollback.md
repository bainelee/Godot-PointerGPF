# Legacy Entry Blocking and Rollback

## Why block legacy entry

To avoid accidental execution from old project-coupled MCP paths, only external package MCP should be used.

## Block behavior

- Legacy MCP execution tools return `LEGACY_MCP_DISABLED`.
- Runtime info can still be queried for diagnostics.

## Emergency rollback switch

- Environment variable: `LEGACY_MCP_EMERGENCY_BYPASS=1`
- Intended only for maintenance and emergency recovery.

## Operational policy

- Default: bypass disabled.
- Use bypass only with explicit change record and audit note.
