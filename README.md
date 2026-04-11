# Pointer GPF V2

This repository now treats `main` as the clean V2 branch.

## What `main` contains

- the V2 Godot MCP rebuild under [v2](/D:/AI/pointer_gpf/v2)
- V2 documentation under [docs](/D:/AI/pointer_gpf/docs)
- V2 regression scripts under [scripts](/D:/AI/pointer_gpf/scripts)

V2 scope is intentionally narrow:

- configure Godot executable
- sync plugin into a target Godot project
- run preflight
- generate project-local `basicflow.json` + `basicflow.meta.json`
- run minimal and interactive file-bridge flows
- support `click`, `wait`, `check`, `closeProject`
- verify teardown after `closeProject`
- reject overlapping flow runs and multiple editor processes for one project

## Recommended entry points

- status: [docs/v2-status.md](/D:/AI/pointer_gpf/docs/v2-status.md)
- architecture: [docs/v2-architecture.md](/D:/AI/pointer_gpf/docs/v2-architecture.md)
- handoff: [docs/v2-handoff.md](/D:/AI/pointer_gpf/docs/v2-handoff.md)
- V2 package root: [v2/README.md](/D:/AI/pointer_gpf/v2/README.md)

## Fixed regression command

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame
```

## Legacy branch

The old MCP system is preserved on the `legacy/mcp` branch for reference only.
`main` should be treated as the only actively maintained branch.
