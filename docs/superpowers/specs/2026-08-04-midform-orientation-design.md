# Mid-Form Video: Orientation & Stitching Design

## Context

The pipeline currently treats each Scene as a standalone vertical 1080x1920 Short
(spec lines 104/109; `SceneRenderer` default 1080x1920, `SceneAssembler` default
1080x1920). Issue #12 requires stitching scenes into one 5-10 min mid-form MP4.

The user clarified their intent: the **master deliverable is landscape 1920x1080**,
and Shorts are derived from it. Issue #12's "1080p horizontal" text and the
spec's "vertical for Shorts compatibility" are contradictory with this intent.

User decisions recorded during brainstorming:

1. **Master orientation**: landscape **1920x1080**.
2. **Shorts strategy**: each Scene is **natively re-rendered at 1080x1920** for its
   Short, never center-cropped from the landscape master (a 16:9 -> 9:16 crop
   discards ~68% of frame width and can cut off stick figures).
3. **Transition style**: **hard cuts** between topics (explainer style). This
   overrides issue #12's "1-second fade transitions" acceptance criterion.
   Rationale: fades dip to black and interrupt explainer pacing; crossfades would
   overlap narration audio (AUDIO is the master clock in `SceneAssembler`).

## Architecture

```
Scene(narration, keywords)
   └── SceneRenderer.render(width=1920, height=1080)      (landscape scene video)
       └── SceneAssembler.assemble(width=1920, height=1080)
           (scene video + VoiceoverGenerator audio -> scene clip MP4)
                                                       ┌───────────────────────┐
            list of assembled scene MP4s ────────────► │  MidformStitcher      │
                                                       │  concatenate_videoclips│
                                                       │  hard cuts             │
                                                       └───────────┬───────────┘
                                                                   ▼
                                                    mid-form MP4 (1920x1080)
```

- **No rework to #9-#11**: `SceneRenderer.render` already accepts `width`/`height`
  overrides (renderer.py:86-100); `SceneAssembler` accepts `width`/`height`
  (assembler.py:31-44) and `_fit_to` cover-fits any target size. The pipeline
  renders/assembles each Scene twice: landscape for the master, vertical for the
  Short. #12's stitcher consumes the landscape assembled clips.
- **Scenes already carry narration audio** (AUDIO is the master clock from #11),
  so stitching concatenates video + audio together — no new sync work.
- **Input contract**: the stitcher only sees finished scene `.mp4` files
  (injected seam, same convention as #9-#11). This keeps tests network-free and
  fast (synthetic clips, no re-render).

## Component: MidformStitcher

New module `src/video_production/stitcher.py`, exported from
`video_production/__init__.py` alongside its siblings.

```python
@dataclass
class StitchResult:
    path: Path
    width: int
    height: int
    duration: float
    scene_count: int

class MidformStitcher:
    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30): ...

    def stitch(self, scene_paths: list[str], output_path: str,
               width: Optional[int] = None,
               height: Optional[int] = None,
               fps: Optional[int] = None) -> StitchResult: ...
```

### Behaviour

- **Concat**: `concatenate_videoclips` (moviepy 2.1.2, `method="chain"`), hard cuts
  between scenes. Scene order preserved.
- **Errors**:
  - empty list or single-scene list -> `ValueError` (no meaningful mid-form)
  - missing scene file -> clear error (probe before concat, not a mid-write glitch)
  - mixed-resolution scenes -> clear `ValueError` (each scene is cover-fitted by
    #11 to the master size; mismatched sizes indicate a caller bug)
- **Export**: `write_videofile(fps, codec="libx264", audio_codec="aac",
  logger=None)` — same conventions as `assembler.py:61-63`.
- **Result**: probe the written file with `VideoFileClip` (like
  assembler.py:68-76) for width/height/duration; `scene_count == len(scene_paths)`.

## Error handling

- Missing input files fail fast (probe each scene before building the composite)
  so the caller sees a clear exception rather than a broken export.
- Resolution consistency is validated up front for the same reason.
- Empty / single scene lists are rejected with `ValueError`.

## Testing

TDD at the seam. Synthetic moviepy fixtures (no re-render, no network):

- **Fixture**: N `ColorClip` "scenes", each written to a tmp `.mp4`. Optionally a
  synthetic sine-wave wav `AudioFileClip` for audio continuity assertions.
- **Cases**:
  1. `stitch` concatenates N scenes -> duration ≈ sum of scene durations,
     `scene_count == N`.
  2. Output probes to 1920x1080 (default) / respects `width`/`height` overrides.
  3. Hard cut present: frame at the scene boundary differs from the previous frame
     (no fade in-between); no audio overlap between scenes.
  4. Empty list -> `ValueError`; single scene -> `ValueError`.
  5. Missing file -> clear error.
  6. Mixed-resolution scenes -> `ValueError`.

## Acceptance criteria (issue #12, revised)

- [ ] Load all scene Short videos in order
- [ ] Stitch into single mid-form video (5-10 minutes, 1920x1080 landscape) with
      hard cuts between topics (overrides "1s fade" criterion)
- [ ] Export as MP4 with good quality/compression balance (libx264/aac)
- [ ] Final video plays smoothly without glitches
- [ ] Tests pass (mid-form file generated, correct duration, scene count)

## Out of scope (this ticket)

- Vertical Short re-render pass (caller concern; renderer/assembler already
  support it).
- Crossfade/fade transition styles (decision: hard cuts).
- Thumbnail generation (issue #13).
- Pipeline orchestration (issues #15-#19).
