# ADR-0001: Landscape master with natively re-rendered vertical Shorts

- **Status**: accepted
- **Date**: 2026-08-04
- **Deciders**: Kevin Lu (user), agent
- **Related**: #12, #9, #10, #11

## Context

The pipeline must produce both a 5-10 minute mid-form video and 3-5 Shorts per
mid-form. The original spec is internally inconsistent: it renders each Scene
at 1080x1920 vertical "for Shorts compatibility" (spec lines 104, 109) while
also describing Short extraction "from each mid-form video" (user story 16) and
exporting the mid-form at "1080p" (spec line 108, ambiguous orientation).

The user clarified their intent: the **primary deliverable is a landscape
1920x1080 mid-form video**, from which Shorts are derived.

## Decision

1. **The master mid-form video is landscape 1920x1080.**
2. **Shorts are never cropped from the landscape master.** A 16:9 -> 9:16
   center-crop discards roughly 68% of the frame width and can cut off stick
   figures. Instead, each Scene is **natively re-rendered at 1080x1920** from the
   same keywords/narration for its Short. This costs a second render pass per
   scene but preserves composition quality in both formats.
3. **Scene-to-scene transitions in the mid-form are hard cuts**, not 1s fades.
   Fades interrupt explainer pacing; crossfades would overlap narration audio
   because `SceneAssembler` uses AUDIO as the master clock.

## Consequences

- `SceneRenderer` and `SceneAssembler` need **no changes** for this decision:
  both already accept `width`/`height` overrides, so scenes render twice at
  different resolutions. The change is in how the pipeline invokes them.
- The mid-form stitcher (#12) concatenates pre-assembled **landscape** scene
  clips with hard cuts.
- Issue #12's "1-second fade transitions" acceptance criterion is superseded.
- Render time roughly doubles per production run (one landscape + one vertical
  render per Scene).
