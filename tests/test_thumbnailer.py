import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import numpy as np
import pytest
from moviepy import ColorClip, ImageClip
from PIL import Image
from video_production.thumbnailer import ThumbnailGenerator, ThumbnailResult

W, H = 1920, 1080
TW, TH = 1280, 720


def bold_font_path():
    for candidate in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ):
        if Path(candidate).exists():
            return candidate
    pytest.skip("no bold sans-serif font available for overlay test")


def make_video(tmp_path, name, duration=5.0, color=(40, 40, 40), size=(W, H)):
    clip = ColorClip(size=size, color=color, duration=duration)
    out = tmp_path / f"{name}.mp4"
    clip.write_videofile(str(out), fps=24, logger=None)
    clip.close()
    return str(out)


def make_twotone_video(tmp_path, name, width, height, white_height, duration=5.0):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:white_height, :, :] = 255
    clip = ImageClip(frame).with_duration(duration)
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
        corner = img.convert("RGB").getpixel((5, 5))
    assert corner == pytest.approx((40, 40, 40), abs=15), "background should survive resize"


def test_thumbnail_draws_high_contrast_text_overlay(tmp_path):
    video = make_video(tmp_path, "ov", color=(20, 120, 220))
    result = ThumbnailGenerator().generate(
        video, "Why Quasars Shine", str(tmp_path / "t.png"), font_path=bold_font_path()
    )
    arr = np.asarray(Image.open(result.path).convert("RGB")).astype(int)
    lower = arr[TH - 260 : TH - 20, 60 : TW - 60]
    dark = int(((lower[:, :, 0] < 90) & (lower[:, :, 1] < 90) & (lower[:, :, 2] < 110)).sum())
    bright = int(
        ((lower[:, :, 0] > 200) & (lower[:, :, 1] > 200) & (lower[:, :, 2] > 200)).sum()
    )
    assert dark > 500, "text backdrop band should darken the lower third"
    assert bright > 50, "bold white glyphs should lighten the band"


def test_thumbnail_raises_on_missing_video(tmp_path):
    with pytest.raises(FileNotFoundError):
        ThumbnailGenerator().generate(
            str(tmp_path / "nope.mp4"), "X", str(tmp_path / "x.png")
        )
    assert not (tmp_path / "x.png").exists()


def test_thumbnail_clamps_frame_time_to_duration(tmp_path):
    video = make_video(tmp_path, "short", duration=1.0)
    result = ThumbnailGenerator().generate(
        video, "Clamp", str(tmp_path / "c.png"), frame_time=60.0
    )
    assert result.frame_time < 1.0


def test_thumbnail_clamps_negative_frame_time(tmp_path):
    video = make_video(tmp_path, "neg")
    result = ThumbnailGenerator().generate(
        video, "Neg", str(tmp_path / "n.png"), frame_time=-5.0
    )
    assert result.frame_time == 0.0
    assert result.path.exists()


def test_thumbnail_cover_fits_non_16x9_source(tmp_path):
    video = make_twotone_video(tmp_path, "portrait", 360, 640, white_height=160)
    result = ThumbnailGenerator().generate(video, "Crop", str(tmp_path / "cf.png"))
    assert result.width == TW
    assert result.height == TH
    with Image.open(result.path) as img:
        corner = img.convert("RGB").getpixel((5, 5))
    assert corner[0] < 60, "cover-fit should center-crop the portrait frame"


def test_thumbnail_handles_empty_title(tmp_path):
    video = make_video(tmp_path, "empty")
    result = ThumbnailGenerator().generate(video, "", str(tmp_path / "e.png"))
    assert result.path.exists()
