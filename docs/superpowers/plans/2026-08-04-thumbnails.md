# Thumbnail Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each task below. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ThumbnailGenerator` in `src/video_production/thumbnailer.py` that extracts a frame from a mid-form MP4 (scene 1 at ~3s), adds a bold sans-serif high-contrast title overlay with Pillow, and exports a 1280x720 PNG thumbnail.

**Architecture:** A new `ThumbnailGenerator` class takes a mid-form MP4 path, a title, and an output path. It extracts the frame at `frame_time` (default 3.0s, clamped to video duration) with MoviePy's `VideoFileClip.get_frame`, cover-fits it to 1280x720, draws a title text overlay (wrapped, bold sans-serif font, white text on a semi-transparent dark backdrop band in the lower third), saves the PNG, then probes the output with Pillow and returns a `ThumbnailResult`. Exported from `video_production/__init__.py` like its siblings.

**Tech Stack:** Python 3.14, MoviePy 2.1.2, Pillow 11.3.0, pytest. No network, no Manim re-render in tests (synthetic `ColorClip` fixture MP4).

**Design context:** ADR-0001 — the mid-form master is landscape 1920x1080, so a thumbnail is a straight downscale of a 16:9 frame to 1280x720 (no crop needed). Shorts are separate vertical re-renders and are out of scope here.

## Global Constraints

- Test runner: `venv\Scripts\python -m pytest -q` (full suite). For one file: `venv\Scripts\python -m pytest tests\test_thumbnailer.py -v`.
- MoviePy 2.1.2 API only: `VideoFileClip` top-level; `clip.size` is a **list** `[w, h]`; `clip.get_frame(t)` returns a **(H, W, 3) numpy array**. NO 1.x kwargs.
- Follow existing `video_production` conventions: dataclass result object, injected seams (input file paths), probe final output, `Path.mkdir(parents=True, exist_ok=True)`.
- Repo test convention: `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))` at top of every test file (duplication with `tests/conftest.py` is known and accepted — follow it).
- Fonts: resolve a bold sans-serif font at runtime (try Windows `C:\Windows\Fonts\arialbd.ttf` / `segoeuib.ttf`, then common Linux paths), falling back to Pillow's built-in font when none exist. Tests inject an explicit font path so results are deterministic on any machine.
- No comments in production code unless asked.

---

### Task 1: ThumbnailGenerator happy path (extract frame + resize + save PNG)

**Files:**
- Create: `src/video_production/thumbnailer.py`
- Test: `tests/test_thumbnailer.py`

**Interfaces:**
- Produces: `ThumbnailResult` dataclass (`path: Path`, `width: int`, `height: int`, `source_path: Path`, `frame_time: float`, `title: str`) and `ThumbnailGenerator.generate(video_path: str, title: str, output_path: str, frame_time: float = 3.0, width=None, height=None, font_path=None) -> ThumbnailResult`. Task 2 adds clamping/validation on top of this.

- [ ] **Step 1: Write the failing test**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from PIL import Image
from moviepy import ColorClip
from video_production.thumbnailer import ThumbnailGenerator, ThumbnailResult

W, H = 1920, 1080
TW, TH = 1280, 720


def make_video(tmp_path, name, duration=5.0, color=(20, 120, 220), size=(W, H)):
    clip = ColorClip(size=size, color=color, duration=duration)
    out = tmp_path / f"{name}.mp4"
    clip.write_videofile(str(out), fps=24, logger=None)
    clip.close()
    return str(out)


def test_thumbnail_extracts_frame_and_saves_png(tmp_path):
    video = make_video(tmp_path, "mid")
    result = ThumbnailGenerator().generate(video, "Test Title", str(tmp_path / "th.png"))
    assert isinstance(result, ThumbnailResult)
    assert result.path.exists()
    assert result.title == "Test Title"
    assert result.source_path == Path(video)


def test_thumbnail_is_1280x720(tmp_path):
    video = make_video(tmp_path, "mid2")
    result = ThumbnailGenerator().generate(video, "Size", str(tmp_path / "s.png"))
    assert result.width == TW
    assert result.height == TH
    with Image.open(result.path) as img:
        assert img.size == (TW, TH)
        assert img.mode == "RGB"


def test_thumbnail_frame_background_matches_source(tmp_path):
    video = make_video(tmp_path, "mid3", color=(40, 40, 40))
    result = ThumbnailGenerator().generate(video, "Bg", str(tmp_path / "b.png"))
    with Image.open(result.path) as img:
        corner = img.getpixel((5, 5))
    assert corner == pytest.approx((40, 40, 40), abs=15), "background should survive resize"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_thumbnailer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'video_production.thumbnailer'`

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image


@dataclass
class ThumbnailResult:
    path: Path
    width: int
    height: int
    source_path: Path
    frame_time: float
    title: str


def _extract_frame(video_path: str, t: float):
    from moviepy import VideoFileClip

    with VideoFileClip(video_path) as clip:
        return clip.get_frame(t)


class ThumbnailGenerator:
    def __init__(self, width: int = 1280, height: int = 720):
        self.width = width
        self.height = height

    def generate(
        self,
        video_path: str,
        title: str,
        output_path: str,
        frame_time: float = 3.0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        font_path: Optional[str] = None,
    ) -> ThumbnailResult:
        width = width or self.width
        height = height or self.height
        frame = _extract_frame(video_path, frame_time)
        img = Image.fromarray(frame).convert("RGB")
        img = img.resize((width, height), Image.LANCZOS)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, format="PNG")
        return ThumbnailResult(
            path=out,
            width=width,
            height=height,
            source_path=Path(video_path),
            frame_time=float(frame_time),
            title=title,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_thumbnailer.py -v`
Expected: 3 passed.

### Task 2: Text overlay with high-contrast bold sans-serif title

**Files:**
- Edit: `src/video_production/thumbnailer.py`, `tests/test_thumbnailer.py`

**Interfaces:**
- Consumes: the `generate(...)` signature from Task 1 (adds `font_path` handling and overlay drawing).
- Produces: text drawn on the thumbnail. The overlay is a semi-transparent dark rounded band in the lower third, with the wrapped title rendered in bold white sans-serif, scaled to fit the band width. No change to the public signature.

- [ ] **Step 1: Write the failing test**

```python
def test_thumbnail_draws_high_contrast_text_overlay(tmp_path):
    video = make_video(tmp_path, "ov")
    result = ThumbnailGenerator().generate(video, "Why Quasars Shine", str(tmp_path / "t.png"))
    with Image.open(result.path) as img:
        px = img.load()
        band = [px[(x, TH - 60)][0] for x in range(100, 400, 20)]
        assert min(band) < 120, "text backdrop band should darken the lower third"
        bright = 0
        for x in range(100, TW - 100, 8):
            for y in range(TH - 90, TH - 30, 8):
                if px[(x, y)][0] > 200 and px[(x, y)][1] > 200 and px[(x, y)][2] > 200:
                    bright += 1
        assert bright > 50, "bold white glyphs should lighten pixels in the band"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL (no overlay drawn yet — band pixels still the source color, bright count ~0).

- [ ] **Step 3: Implement the overlay**

Add font resolution, text wrapping, band, and glyph drawing to `generate`. Wrap title to a max line width; pick font size by scaling down until the wrapped text fits the band; draw a translucent black rounded rectangle, then white bold text with a subtle shadow for contrast. Fall back to Pillow's `ImageFont.load_default(size=...)` (Pillow 11) when no truetype font resolves.

- [ ] **Step 4: Run test to verify it passes**

Expected: 4 passed.

### Task 3: Error handling and frame-time clamping

**Files:**
- Edit: `src/video_production/thumbnailer.py`, `tests/test_thumbnailer.py`

**Interfaces:**
- Consumes: `generate(...)` from Task 2.
- Produces: `FileNotFoundError` for a missing video, frame-time clamped to the video duration (so `frame_time` past the end still produces a thumbnail), empty title handled without crashing (still produces a readable thumbnail).

- [ ] **Step 1: Write the failing test**

```python
def test_thumbnail_raises_on_missing_video(tmp_path):
    with pytest.raises(FileNotFoundError):
        ThumbnailGenerator().generate(str(tmp_path / "nope.mp4"), "X", str(tmp_path / "x.png"))


def test_thumbnail_clamps_frame_time_to_duration(tmp_path):
    video = make_video(tmp_path, "short", duration=1.0)
    result = ThumbnailGenerator().generate(video, "Clamp", str(tmp_path / "c.png"), frame_time=60.0)
    assert result.frame_time < 1.0


def test_thumbnail_handles_empty_title(tmp_path):
    video = make_video(tmp_path, "empty")
    result = ThumbnailGenerator().generate(video, "", str(tmp_path / "e.png"))
    assert result.path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Expected: `FileNotFoundError`/clamp/empty-title tests fail with the Task-2 code.

- [ ] **Step 3: Implement**

Before extraction: `Path(video_path).exists()` check → `FileNotFoundError`. Probe `VideoFileClip.duration` (reusing the same open) and clamp `frame_time = min(frame_time, max(0.0, duration - 0.05))`. Empty title: skip band/glyph drawing entirely but still return a valid result.

- [ ] **Step 4: Run test to verify it passes**

Expected: 7 passed.

### Task 4: Export from package

**Files:**
- Edit: `src/video_production/__init__.py`

Add `ThumbnailGenerator` and `ThumbnailResult` to the `from .thumbnailer import ...` line and `__all__`.

### Task 5: Full suite, review, commit

- [ ] Run: `venv\Scripts\python -m pytest -q` → all tests pass (existing 150 + new).
- [ ] Code review of `thumbnailer.py` + `test_thumbnailer.py` (standards + spec).
- [ ] Commit to `master`, push, close #13 with a summary comment (no secrets in messages).
