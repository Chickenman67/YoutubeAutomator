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
