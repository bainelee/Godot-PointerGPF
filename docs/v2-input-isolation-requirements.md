# V2 Input Isolation Requirements

## Purpose

This document records the input-isolation requirement for V2 runtime testing.

The target user scenario is:

- the developer runs GPF on the same Windows machine that also has:
  - an AI IDE
  - the Godot editor
  - the Godot game process started by GPF
- the developer may have only one screen
- while GPF is running a flow, the developer must be able to keep using the computer
- the developer's real mouse and keyboard activity must not affect the game process under test

## Required Outcome

During automated flow execution:

1. GPF-controlled game actions and user desktop actions must be separated
2. real user input must not change the tested game state
3. the tested game window must not require the user to avoid clicks, movement, or key presses manually

This is stronger than:

- "do not capture the mouse"
- "do not move the cursor too much"
- "try to stay out of the way"

The requirement is full isolation from real user input, not just reduced interference.

## Observed Evidence

Observed on `D:\AI\pointer_gpf_testgame`:

- a flow that only launched the game and waited for `StartButton` did **not** capture the mouse
- a flow that clicked `StartButton` and entered `GameLevel` **did** capture the mouse

Relevant project code:

- [fps_controller.gd](/D:/AI/pointer_gpf_testgame/scripts/player/fps_controller.gd)

Important details in that script:

- `_apply_pointer_ui_mouse_mode()` sets `Input.mouse_mode`
- `_physics_process()` reads real input state through APIs such as:
  - `Input.is_action_just_pressed(...)`
  - `Input.is_key_pressed(...)`
- `_input()` also reacts to real mouse motion and button input

## Architectural Consequence

Because the tested project can read real input state directly from `Input`, event-layer mitigation inside the runtime bridge is not enough.

Examples of insufficient fixes:

- forcing `Input.mouse_mode = VISIBLE`
- swallowing some `_input(event)` callbacks in the bridge
- switching the player into a UI pointer mode

These may reduce symptoms, but they do not guarantee isolation.

If the game window is still running on the same interactive desktop and is allowed to receive real OS input, project code can still poll that state and change gameplay.

## V2 Requirement

V2 should treat "same interactive desktop + real user input can still reach the game window" as **not isolated**.

So the long-term fix must move beyond bridge-side mouse-mode patches.

## Acceptable Direction

Future implementation should aim for one of these classes of solution:

1. run the tested game in an execution environment isolated from the user's current desktop/session
2. run the tested game through a backend where GPF actions are injected through a private control channel and real user input cannot reach the target runtime

Whichever path is chosen, the acceptance bar stays the same:

- while a flow is running, the user can keep using the computer normally
- the user cannot accidentally alter the game state under test

## Current Status

Current V2 can reduce some cursor-capture symptoms, but it does **not** yet satisfy the full input-isolation requirement above.
