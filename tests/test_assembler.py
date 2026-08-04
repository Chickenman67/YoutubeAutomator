import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from video_production.assembler import AssemblyResult, SceneAssembler

W, H = 1080, 1920


def make_video(tmp_path, size=(540, 960), duration=2.0, name="input.mp4"):
    from moviepy import ColorClip

    path = tmp_path / name
    clip = ColorClip(size=size, color=(40, 40, 40), duration=duration)
    clip.write_videofile(str(path), fps=24, logger=None)
    clip.close()
    return str(path)


def make_audio(tmp_path, duration=2.0, name="input.wav"):
    path = tmp_path / name
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * duration))
    return str(path)


def test_assemble_outputs_vertical_short_with_audio(tmp_path):
    assembler = SceneAssembler()
    result = assembler.assemble(
        make_video(tmp_path), make_audio(tmp_path), str(tmp_path / "short.mp4")
    )
    assert isinstance(result, AssemblyResult)
    assert result.path.exists()
    assert result.width == W
    assert result.height == H
    assert result.duration == pytest.approx(2.0, abs=0.2)
    assert result.has_audio is True


def test_assemble_fits_any_input_size_to_vertical(tmp_path):
    assembler = SceneAssembler()
    result = assembler.assemble(
        make_video(tmp_path, size=(1280, 720), duration=2.0),
        make_audio(tmp_path, duration=2.0),
        str(tmp_path / "wide.mp4"),
    )
    assert result.width == W
    assert result.height == H


def test_assemble_audio_is_master_clock_when_video_shorter(tmp_path):
    assembler = SceneAssembler()
    result = assembler.assemble(
        make_video(tmp_path, duration=1.0, name="shortvid.mp4"),
        make_audio(tmp_path, duration=2.5, name="longau.wav"),
        str(tmp_path / "frozen.mp4"),
    )
    assert result.duration == pytest.approx(2.5, abs=0.2)
    assert result.has_audio is True


def test_assemble_trims_video_longer_than_audio(tmp_path):
    assembler = SceneAssembler()
    result = assembler.assemble(
        make_video(tmp_path, duration=4.0, name="longvid.mp4"),
        make_audio(tmp_path, duration=2.0),
        str(tmp_path / "trimmed.mp4"),
    )
    assert result.duration == pytest.approx(2.0, abs=0.2)
