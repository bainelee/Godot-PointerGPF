# V2 Input Isolation Plan

## Purpose

This plan turns the requirement in [v2-input-isolation-requirements.md](/D:/AI/pointer_gpf/docs/v2-input-isolation-requirements.md) into an implementation path.

Goal:

- while GPF runs a Godot flow, the developer can keep using the same Windows machine
- real user mouse and keyboard input must not affect the tested game process
- GPF actions and user desktop actions must be separated

## Current Facts

Current V2 runtime model:

- launches the Godot editor on the user's current interactive desktop
- enters editor `play_mode`
- drives the game through the in-project runtime bridge
- still allows the project under test to read real input through Godot `Input`

Observed on `D:\AI\pointer_gpf_testgame`:

- launching into the startup scene does not by itself capture the mouse
- clicking `StartButton` and entering `GameLevel` leads to mouse capture
- the game project reads real input inside gameplay code such as `fps_controller.gd`

Conclusion:

- bridge-side mouse-mode patches cannot provide true isolation
- as long as the tested game is running on the same interactive desktop and can read real OS input, the user can still affect gameplay

## Options

### Option A: stay in current desktop and try to suppress input in-engine

Possible method:

- add automation flags in the runtime bridge
- patch project code or inject wrappers to swallow `_input`, `_unhandled_input`, and some `Input` reads during automation

Problems:

- cannot reliably cover arbitrary project code that polls `Input` directly
- fragile across different Godot projects
- mixes testing infrastructure with project gameplay behavior
- does not fully prevent focus or foreground-window interference

Decision:

- reject as the main solution

### Option B: run the tested game in an isolated execution surface on the same machine

Possible method:

- launch the game/runtime inside a separate Windows desktop or other isolated session/surface
- keep the bridge channel for commands/results
- do not rely on the user's current foreground desktop

Benefits:

- real user input on the main desktop does not reach the tested runtime
- preserves the current file-bridge architecture
- does not require patching each game project's input code

Risks:

- Windows desktop/session handling is more complex than the current `play_mode` flow
- may require moving beyond editor `play_mode` for full reliability
- needs process-launch, visibility, and teardown rules specific to the isolated surface

Decision:

- recommended primary direction

### Option C: run the tested game in a separate VM / remote worker / dedicated display environment

Benefits:

- strongest isolation
- easiest to reason about from a correctness perspective

Problems:

- higher setup and operating cost
- heavier than the current V2 product scope
- slows down the path to a practical local workflow

Decision:

- keep as a fallback or later expansion, not the first local V2 implementation

## Recommended Direction

Use Option B as the V2 next step:

1. stop treating editor `play_mode` on the user's current desktop as the long-term execution model
2. introduce a dedicated isolated execution surface for the game runtime
3. keep the runtime bridge contract, flow runner, and asset model as much as possible
4. prove that user activity on the main desktop does not affect the running flow

## Phased Plan

### Phase 1: isolate the runtime contract from editor `play_mode`

Target:

- make runtime execution launchable without depending on the user's current foreground editor play session

Tasks:

- define a new runtime launch mode alongside current `play_mode`
- decide which process owns the runtime bridge in isolated mode
- separate "editor open for project management" from "runtime process under test"
- keep existing `command.json` / `response.json` / diagnostics contract if possible

Acceptance:

- one command can start the isolated runtime process
- `run_basic_flow` can target that process through the existing bridge contract
- teardown can verify that isolated runtime stopped, without using the user-visible game window as the main signal

### Phase 2: add isolated execution-surface launcher on Windows

Target:

- launch the tested runtime on a surface that does not receive the user's normal desktop input

Tasks:

- choose the Windows isolation primitive
- define process-launch and teardown ownership
- record isolated-runtime metadata in V2 diagnostics and reports
- ensure stale-lock and multi-process checks distinguish editor process vs isolated runtime process

Acceptance:

- while a flow is running, the user can keep moving and clicking on the main desktop
- the tested runtime still advances correctly through flow steps
- user input on the main desktop does not alter game state in the tested runtime

### Phase 3: tighten flow actions so they only use private automation channels

Target:

- remove any remaining dependence on user-desktop input semantics

Tasks:

- audit `click`, `wait`, `check`, and future actions for direct OS-input assumptions
- prefer direct node invocation, signal emission, and internal scene queries over desktop-like input simulation
- keep fallback coordinate clicks only where they can be proven isolated inside the runtime surface

Acceptance:

- flow actions still pass if the user is actively using mouse and keyboard on the main desktop
- the test project cannot be moved off course by accidental user interaction

### Phase 4: add verification for the isolation guarantee

Target:

- make input isolation a regression-tested contract, not just an implementation claim

Tasks:

- add a fixed validation scenario that continuously generates user-like activity on the main desktop or a synthetic substitute while the flow runs
- assert that the tested runtime still reaches the expected nodes and final checks
- add clear report fields describing the execution mode and isolation mode used

Acceptance:

- regression bundle proves flow success under concurrent non-test user activity

## Explicit Non-Goals

Do not treat these as the fix:

- forcing `Input.mouse_mode = VISIBLE`
- switching the player into a UI pointer mode
- asking the user not to touch mouse or keyboard while a flow runs
- documenting a manual workaround instead of changing the execution model

## Immediate Next Implementation Task

Start with a short technical spike that answers these concrete questions:

1. which Windows isolation primitive is feasible for local V2
2. whether isolated mode should still use the editor process, or must launch a separate runtime process
3. what minimum changes are needed in `server.py`, `plugin.gd`, and `runtime_bridge.gd` to support that mode

The spike output should be:

- one chosen direction
- one rejected fallback direction
- a concrete file-level change list for the first implementation slice

## Spike Conclusion

### Chosen Direction

Chosen direction:

- move local V2 runtime execution away from editor `play_mode` on `Winsta0\default`
- launch the tested runtime process onto a dedicated Windows desktop on the same machine
- keep GPF itself and the developer on the normal interactive desktop
- keep the bridge-based control model, but point it at the isolated runtime process instead of the user-visible editor play session

Reasoning:

- Microsoft documents that processes started by the logged-on user are normally associated with `Winsta0\default`, and that a process can create another desktop and start processes on it through the `STARTUPINFO.lpDesktop` path
- this is the smallest local change that can create real separation without immediately introducing a VM or remote worker
- it also aligns with the current V2 architecture, because V2 already prefers explicit runtime files and a narrow bridge contract over heavy orchestration

Practical implication:

- isolated mode should launch a separate Godot runtime process
- it should not depend on `EditorInterface.play_main_scene()` for the actual game run

### Rejected Fallback

Rejected fallback:

- trying to guarantee isolation by swallowing input inside the current runtime bridge while still running the game on the user's current desktop

Reason:

- game code can poll real input directly through Godot `Input`
- event-layer suppression, mouse-mode changes, or forcing UI pointer mode cannot prove isolation
- this path leaves the core correctness issue unsolved

## First Implementation Slice

The first slice should create a new isolated runtime mode without deleting the current validated `play_mode` path yet.

### Scope

Add an experimental parallel path:

- current mode:
  - editor plugin launches editor
  - editor enters `play_mode`
  - runtime bridge inside the project consumes commands
- new isolated mode:
  - Python launches Godot runtime directly onto a dedicated desktop
  - runtime bridge inside the game process consumes commands
  - editor remains optional for project preparation, but does not own the tested runtime session

### File-Level Change List

#### 1. [server.py](/D:/AI/pointer_gpf/v2/mcp_core/server.py)

Add:

- a new execution-mode selector for `run_basic_flow`
- launch logic for isolated runtime mode
- teardown verification for isolated runtime process identity, not just editor play-mode state
- reporting fields that say which execution mode ran

Change:

- split `_ensure_play_mode()` into mode-specific launch helpers
- keep the current `play_mode` path for regression continuity

#### 2. [flow_runner.py](/D:/AI/pointer_gpf/v2/mcp_core/flow_runner.py)

Add:

- execution metadata fields for the runtime process under test
- optional wait-for-runtime-ready handshake that does not assume editor play-mode ownership

Change:

- avoid baking editor-specific assumptions into the runner lifecycle

#### 3. [plugin.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/plugin.gd)

Change:

- reduce responsibility to editor-side project preparation only
- keep `runtime_gate.json` support for current mode
- do not make isolated runtime depend on editor polling as its primary truth source

#### 4. [runtime_bridge.gd](/D:/AI/pointer_gpf/v2/godot_plugin/addons/pointer_gpf/runtime_bridge.gd)

Add:

- an explicit runtime-session identity file or response field so Python can verify it is talking to the isolated runtime instance it launched
- an isolated-mode lifecycle marker that does not depend on editor state

Change:

- keep command handling bridge-only and avoid new user-input workarounds here

#### 5. new module under [v2/mcp_core](/D:/AI/pointer_gpf/v2/mcp_core)

Create:

- a Windows-specific launcher module for isolated desktop runtime startup and teardown

Likely responsibilities:

- create/open the dedicated desktop
- launch Godot with `STARTUPINFO.lpDesktop`
- track the runtime PID and session metadata
- close or recycle the desktop after teardown

#### 6. tests

Add:

- unit tests for execution-mode selection in [test_server.py](/D:/AI/pointer_gpf/v2/tests/test_server.py)
- unit tests for the isolated-launch metadata contract
- a fixed integration validation command once the first slice can actually launch on an isolated desktop

## Acceptance Bar For Slice 1

Slice 1 is complete only if:

1. V2 can launch a Godot runtime process in isolated mode
2. the bridge can execute at least the minimal `launchGame -> closeProject` chain against that runtime
3. the result payload clearly identifies isolated mode
4. the existing `play_mode` path still passes the current regression bundle until the isolated path is ready to replace it
