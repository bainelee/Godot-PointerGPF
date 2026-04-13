# V2 Release And Install

This document describes the current minimal release shape for Pointer GPF V2.

## Current Release Goal

The current release goal is modest:

- produce a zip bundle that contains the runnable V2 source tree
- let a user unzip it and run the V2 server with Python
- verify the bundle by unpacking it and running a smoke check

This is not yet a polished installer.
It is a verified source-bundle release path.

## Build A Release Bundle

From the repository root:

```powershell
python D:\AI\pointer_gpf\scripts\build-v2-release.py --version 0.0.0-local
```

This creates:

- `dist/pointer-gpf-v2-<version>.zip`

The bundle currently includes:

- root README files
- logo
- `docs/`
- `scripts/`
- `v2/`

It intentionally excludes:

- `.git/`
- `.github/`
- `dist/`
- root `tmp/`
- `__pycache__/`

## Verify A Release Bundle

After building the zip, verify it with:

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-release-package.py --bundle D:\AI\pointer_gpf\dist\pointer-gpf-v2-0.0.0-local.zip --project-root D:\AI\pointer_gpf_testgame
```

The verification does three things:

1. unpack the bundle into a temporary directory
2. confirm key files exist in the unpacked release
3. run:
   - `python -m unittest discover -s v2/tests -p "test_*.py"`
   - `python -m v2.mcp_core.server --tool get_user_request_command_guide --project-root ...`

If those pass, the bundle has at least been proven to be:

- structurally complete
- importable
- runnable as a V2 MCP source bundle

## Current User Install Assumption

The current minimal release assumes the user has:

- Python 3.11+
- a Windows environment compatible with the current V2 scripts
- a Godot project path to target

The current release path does not yet provide:

- a native installer
- a pip package
- a one-click MCP client installer

## What This Release Validation Proves

It proves:

- the release zip contains the required V2 files
- the unpacked release can run the V2 test suite
- the unpacked release can launch the current command-guide server entry

It does not yet prove:

- a fully polished end-user setup flow
- client-specific MCP installation UX
- cross-platform packaging
