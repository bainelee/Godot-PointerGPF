# Figma -> GPF UI Sync Report (2026-04-09)

## Goal

Synchronize the Figma screen (`fileKey=ECtrl9ymwWk9qyMH6glaZj`, `nodeId=1:3`) into `examples/godot_minimal`, and harden the GPF verification/fix loop so UI compare, annotation, approval, and suggestion are reusable.

## What Was Implemented

- Added Figma collaboration toolchain in MCP:
  - `figma_design_to_baseline`
  - `compare_figma_game_ui`
  - `annotate_ui_mismatch`
  - `approve_ui_fix_plan`
  - `suggest_ui_fix_patch`
- Added approval gate requirement (`approved=true`) before fix suggestions.
- Added reusable image-size strategy:
  - parameterized `image_target_height`
  - generated `uniform_scale_plan` with node-level `scale_factor` and `patch_hint`
- Improved compare reliability:
  - auto-convert non-PNG baseline inputs to PNG
  - allow summary artifact (`compare_figma_game_ui_last.json`) as upstream input for follow-up tools
  - support resize-based compare (`resize_to_baseline`)
  - switched pixel difference metric to normalized MAD instead of raw byte inequality count

## Example Project Sync Results

- Synced `examples/godot_minimal/scenes/main_scene_example.tscn` to match Figma layout blocks:
  - title area
  - 3 preview images
  - bottom bar and labels
- Replaced preview textures with latest Figma-provided source assets (`figma_image_1/2/3.png`).
- Added screenshot capture script for deterministic runtime capture:
  - `examples/godot_minimal/scripts/capture_ui_screenshot.gd`

## Verification Workflow Executed

For `examples/godot_minimal`:

1. `figma_design_to_baseline`
2. `compare_figma_game_ui`
3. `annotate_ui_mismatch`
4. `approve_ui_fix_plan`
5. `suggest_ui_fix_patch`

Latest run produced:

- `overall_status`: `fail`
- `visual_diff.pixel_diff_ratio`: `0.329572`
- `visual_diff.perceptual_score`: `0.670428`
- `layout_diff.dimension_mismatch`: `false`

Interpretation:

- Core geometry is aligned (frame dimensions and principal regions).
- Remaining gap is mostly visual/detail-level (text rasterization, anti-aliasing, texture/fit behavior nuances), not gross layout breakage.

## Main Files Changed

- `mcp/server.py`
- `mcp/adapter_contract_v1.json`
- `scripts/assert-mcp-artifacts.ps1`
- `.github/workflows/mcp-smoke.yml`
- `.github/workflows/mcp-integration.yml`
- `examples/godot_minimal/project.godot`
- `examples/godot_minimal/scenes/main_scene_example.tscn`
- `examples/godot_minimal/scripts/capture_ui_screenshot.gd`
- `examples/godot_minimal/assets/*` (Figma images and captures)
- `tests/test_figma_ui_pipeline.py`
- docs and changelog updates (`README.md`, `docs/quickstart.md`, `docs/mcp-testing-spec.md`, `docs/mcp-implementation-status.md`, `docs/godot-adapter-contract-v1.md`, `CHANGELOG.md`)

## Next Suggested Step

Run one more polish pass focused on typography/text rendering and bottom-bar label alignment, then re-run the same MCP pipeline to target `pixel_diff_ratio < 0.25`.
