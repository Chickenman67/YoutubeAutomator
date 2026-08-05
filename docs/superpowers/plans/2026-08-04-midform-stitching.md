# Mid-Form Video Stitching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `MidformStitcher` in `src/video_production/stitcher.py` that concatenates pre-assembled landscape scene MP4s (each with narration audio) into one 1920x1080 mid-form MP4 with hard cuts.

**Architecture:** A new `MidformStitcher` class takes a list of assembled scene MP4 paths, validates them (≥2 scenes, files exist, all 1920x1080), concatenates them with MoviePy's `concatenate_videoclips(method="chain")` producing hard cuts between topics, writes an MP4 (libx264/aac), then probes the output with `VideoFileClip` and returns a `StitchResult`. Exported from `video_production/__init__.py` like its siblings.

**Tech Stack:** Python 3.14, MoviePy 2.1.2, pytest. No network, no Manim re-render in tests (synthetic `ColorClip` fixtures).

**Design spec:** `docs/superpowers/specs/2026-08-04-midform-orientation-design.md` (ADR-0001).

## Global Constraints

- Test runner: `venv\Scripts\python -m pytest -q` (full suite). For one file: `venv\Scripts\python -m pytest tests\test_stitcher.py -v`.
- MoviePy 2.1.2 API only: `VideoFileClip`/`AudioFileClip`/`ColorClip` top-level; `concatenate_videoclips(clips, method="chain")` (verified signature); `write_videofile(fps, codec, audio_codec, logger=None)`. NO 1.x kwargs like `final_frame=`.
- Follow existing `video_production` conventions: dataclass result objects, injected seams (input file paths), probe final output with `VideoFileClip`, `write_videofile(..., logger=None)`, `Path.mkdir(parents=True, exist_ok=True)`.
- Repo test convention: `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))` at top of every test file (duplication with `tests/conftest.py` is known and accepted — follow it).
- Output is the **landscape** master: 1920x1080. Vertical 1080x1920 Short rendering is a separate pipeline concern (out of scope here).
- No comments in production code unless asked.

---

### Task 1: MidformStitcher happy path (concatenate + probe)

**Files:**
- Create: `src/video_production/stitcher.py`
- Test: `tests/test_stitcher.py`

**Interfaces:**
- Consumes: nothing from prior tasks; relies on moviepy 2.1.2.
- Produces: `StitchResult` dataclass and `MidformStitcher.stitch(scene_paths: list[str], output_path: str, width=None, height=None, fps=None) -> StitchResult`. Task 2 adds validation on top of this.

- [ ] **Step 1: Write the failing test**

```python
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from moviepy import AudioFileClip, ColorClip, VideoFileClip
from video_production.stitcher import MidformStitcher, StitchResult

W, H = 1920, 1080


def make_audio(tmp_path, name, duration=1.0):
    path = tmp_path / f"{name}.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * duration))
    return str(path)


def make_scene(tmp_path, name, duration=1.0, color=(40, 40, 40), size=(W, H)):
    audio = AudioFileClip(make_audio(tmp_path, name, duration))
    video = ColorClip(size=size, color=color, duration=duration).with_audio(audio)
    out = tmp_path / f"{name}.mp4"
    video.write_videofile(str(out), fps=24, logger=None)
    video.close()
    audio.close()
    return str(out)


def test_stitch_concatenates_scenes_in_order(tmp_path):
    paths = [make_scene(tmp_path, f"s{i}", duration=1.0) for i in range(3)]
    result = MidformStitcher().stitch(paths, str(tmp_path / "mid.mp4"))
    assert isinstance(result, StitchResult)
    assert result.path.exists()
    assert result.scene_count == 3
    assert result.width == W
    assert result.height == H
    assert result.duration == pytest.approx(3.0, abs=0.2)


def test_stitch_keeps_audio_with_total_duration(tmp_path):
    paths = [
        make_scene(tmp_path, "a1", duration=1.5),
        make_scene(tmp_path, "a2", duration=0.8),
    ]
    result = MidformStitcher().stitch(paths, str(tmp_path / "au.mp4"))
    assert result.duration == pytest.approx(2.3, abs=0.2)
    with VideoFileClip(str(result.path)) as clip:
        assert clip.audio is not None
        assert clip.audio.duration == pytest.approx(2.3, abs=0.2)


def test_stitch_respects_dimension_override(tmp_path):
    size = (320, 180)
    paths = [
        make_scene(tmp_path, "o1", size=size),
        make_scene(tmp_path, "o2", size=size),
    ]
    result = MidformStitcher().stitch(
        paths, str(tmp_path / "o.mp4"), width=320, height=180
    )
    assert result.width == 320
    assert result.height == 180
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_stitcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'video_production.stitcher'`

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class StitchResult:
    path: Path
    width: int
    height: int
    duration: float
    scene_count: int


class MidformStitcher:
    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps

    def stitch(
        self,
        scene_paths: list[str],
        output_path: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
    ) -> StitchResult:
        from moviepy import VideoFileClip, concatenate_videoclips

        width = width or self.width
        height = height or self.height
        fps = fps or self.fps

        clips = []
        composite = None
        try:
            for scene in scene_paths:
                clips.append(VideoFileClip(str(scene)))

            composite = concatenate_videoclips(clips, method="chain")

            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            composite.write_videofile(
                str(out), fps=int(fps), codec="libx264", audio_codec="aac", logger=None
            )
        finally:
            if composite is not None:
                composite.close()
            for clip in clips:
                clip.close()

        with VideoFileClip(str(out)) as final:
            out_width, out_height = final.size
            return StitchResult(
                path=out,
                width=int(out_width),
                height=int(out_height),
                duration=float(final.duration),
                scene_count=len(scene_paths),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_stitcher.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/video_production/stitcher.py tests/test_stitcher.py
git commit -m "Add mid-form stitching combining scene clips via MoviePy (#12)"
```

---

### Task 2: Stitcher input validation

**Files:**
- Modify: `src/video_production/stitcher.py`
- Test: `tests/test_stitcher.py` (append)

**Interfaces:**
- Consumes: `MidformStitcher` from Task 1 (unchanged signature).
- Produces: hardened `stitch()` — rejects <2 scenes, missing files, size mismatch.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stitcher.py`:

```python
def test_stitch_requires_at_least_two_scenes(tmp_path):
    stitcher = MidformStitcher()
    with pytest.raises(ValueError):
        stitcher.stitch([], str(tmp_path / "e.mp4"))
    with pytest.raises(ValueError):
        stitcher.stitch([make_scene(tmp_path, "only")], str(tmp_path / "e2.mp4"))


def test_stitch_raises_on_missing_scene_file(tmp_path):
    good = make_scene(tmp_path, "g")
    with pytest.raises(FileNotFoundError):
        MidformStitcher().stitch(
            [good, str(tmp_path / "nope.mp4")], str(tmp_path / "m.mp4")
        )


def test_stitch_rejects_mixed_resolutions(tmp_path):
    big = make_scene(tmp_path, "big", size=(W, H))
    small = make_scene(tmp_path, "small", size=(320, 180))
    with pytest.raises(ValueError):
        MidformStitcher().stitch([big, small], str(tmp_path / "mix.mp4"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_stitcher.py -v`
Expected: 3 FAIL (no validation raised yet — concatenation proceeds or raises a different error)

- [ ] **Step 3: Implement validation**

Edit `stitch()` in `src/video_production/stitcher.py`:

1. At the top of `stitch()`, before opening any clip:

```python
        if len(scene_paths) < 2:
            raise ValueError("need at least two scenes to stitch a mid-form video")
```

2. Inside the `for scene in scene_paths:` loop, replace `clips.append(VideoFileClip(str(scene)))` with:

```python
            path = Path(scene)
            if not path.exists():
                raise FileNotFoundError(f"scene video not found: {path}")
            clips.append(VideoFileClip(str(path)))
```

3. After the loop (before `concatenate_videoclips`), add:

```python
            for clip in clips:
                if clip.size != (width, height):
                    raise ValueError(
                        f"scene size {clip.size} does not match target {(width, height)}"
                    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_stitcher.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/video_production/stitcher.py tests/test_stitcher.py
git commit -m "Validate stitcher inputs: min scenes, existence, resolution (#12)"
```

---

### Task 3: Hard-cut transition verification

**Files:**
- Test: `tests/test_stitcher.py` (append)

**Interfaces:**
- Consumes: `MidformStitcher` from Task 2 (unchanged signature).
- Produces: regression proof that concatenation produces hard cuts, not fades (no new production code — `method="chain"` already does this).

- [ ] **Step 1: Write the test**

Append to `tests/test_stitcher.py`:

```python
def test_stitch_cuts_hard_between_scenes(tmp_path):
    red = make_scene(tmp_path, "red", duration=1.0, color=(255, 0, 0))
    blue = make_scene(tmp_path, "blue", duration=1.0, color=(0, 0, 255))
    result = MidformStitcher().stitch([red, blue], str(tmp_path / "cut.mp4"))
    assert result.duration == pytest.approx(2.0, abs=0.2)
    with VideoFileClip(str(result.path)) as clip:
        before = clip.get_frame(0.5)
        boundary = clip.get_frame(1.0)
        after = clip.get_frame(1.5)
    assert before[0][0] > before[0][2], "frame before boundary should be red"
    assert after[0][2] > after[0][0], "frame after boundary should be blue"
    assert abs(int(boundary[0][0]) - int(boundary[0][2])) > 60, (
        "boundary frame must be one scene or the other, not a fade blend"
    )
```

- [ ] **Step 2: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_stitcher.py::test_stitch_cuts_hard_between_scenes -v`
Expected: PASS (hard cut already provided by `concatenate_videoclips(method="chain")`). If it fails with a blend at the boundary, a fade was introduced and must be removed.

- [ ] **Step 3: Run full stitcher file**

Run: `venv\Scripts\python -m pytest tests\test_stitcher.py -v`
Expected: 7 PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_stitcher.py
git commit -m "Verify hard cuts between mid-form scenes (#12)"
```

---

### Task 4: Export from package + full suite + spec line update

**Files:**
- Modify: `src/video_production/__init__.py`
- Modify: `docs/spec.md` (line 108)

**Interfaces:**
- Consumes: `MidformStitcher`, `StitchResult` from Task 2.
- Produces: package-level `video_production.MidformStitcher` / `video_production.StitchResult`; spec line 108 no longer contradicts ADR-0001.

- [ ] **Step 1: Export from package**

Edit `src/video_production/__init__.py`:

```python
from .assembler import AssemblyResult, SceneAssembler
from .renderer import RenderResult, SceneRenderer
from .stitcher import MidformStitcher, StitchResult
from .tts import DEFAULT_VOICE, VoiceoverGenerator, VoiceoverResult, probe_audio_duration
from . import stickfigures

__all__ = [
    "AssemblyResult",
    "DEFAULT_VOICE",
    "MidformStitcher",
    "RenderResult",
    "SceneAssembler",
    "SceneRenderer",
    "StitchResult",
    "VoiceoverGenerator",
    "VoiceoverResult",
    "probe_audio_duration",
    "stickfigures",
]
```

- [ ] **Step 2: Update spec line 108**

Edit `docs/spec.md:108`. Replace:

```markdown
- **Mid-form assembly**: Stitch all scenes with MoviePy, add transitions (1s fade), export as 1080p MP4
```

with:

```markdown
- **Mid-form assembly**: Stitch all landscape 1920x1080 scene clips with MoviePy, hard cuts between topics (see ADR-0001), export as MP4
```

- [ ] **Step 3: Verify package import works**

Run: `venv\Scripts\python -c "from video_production import MidformStitcher, StitchResult; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Run full suite**

Run: `venv\Scripts\python -m pytest -q`
Expected: all PASS (previous suite was 142 passed, 1 skipped; now 149 passed + 1 skipped)

- [ ] **Step 5: Commit**

```bash
git add src/video_production/__init__.py docs/spec.md
git commit -m "Export MidformStitcher and document hard-cut assembly (closes #12)"
```

---

## Self-Review

- **Spec coverage:** Spec sections — component location/API (Task 1), behaviour/concat + hard cuts (Task 1 impl + Task 3), error handling (Task 2: ≥2 scenes, missing file, resolution), export/conventions (Task 1 step 3, Task 4), testing (Tasks 1-3), acceptance criteria (all tasks). ADR consequence "update issue #12 acceptance" was done during brainstorming. Spec "out of scope" items (vertical Short re-render, crossfade, thumbnails, orchestration) correctly not implemented.
- **Placeholder scan:** no TBD/TODO/"add appropriate error handling" without code — every step has concrete code or commands.
- **Type consistency:** `StitchResult.path/width/height/duration/scene_count`, `MidformStitcher(width, height, fps)` defaults 1920/1080/30, `stitch(scene_paths, output_path, width=None, height=None, fps=None)` — identical across all four tasks. `make_scene(tmp_path, name, duration, color, size)` fixture consistent in every test.
