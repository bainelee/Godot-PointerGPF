# Scripts

This branch is V2-only.

## Supported scripts

| Script | Purpose |
| --- | --- |
| `scripts/build-v2-release.py` | Build a minimal V2 source-bundle release zip under `dist/`. |
| `scripts/verify-v2-regression.py` | Run the fixed V2 regression bundle: unit tests, preflight, interactive flow, basicflow question contract, session generation, default project basicflow run, stale analysis, stale override, and runtime guards. |
| `scripts/verify-v2-release-package.py` | Unpack a built V2 release bundle and smoke-verify that the release remains runnable. |
| `scripts/verify-v2-runtime-guards.py` | Verify V2 runtime protections: reject overlapping flow runs for one project and reject multiple Godot editor processes for the same project. |

## Legacy branch

Old MCP packaging, release, migration, and legacy verification scripts were removed from `main`.
Use the `legacy/mcp` branch if you need to inspect or reuse them.
