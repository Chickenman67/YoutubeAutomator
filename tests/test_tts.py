import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from script_generation.schema import Scene
from video_production.tts import (
    DEFAULT_VOICE,
    VoiceoverGenerator,
    VoiceoverResult,
    _chunk_narration,
)


def make_scene(narration="word " * 200):
    return Scene(
        scene_id=1,
        narration=narration,
        key_visual_keywords=["a", "b", "c"],
        facts=["a verifiable fact", "another verifiable fact"],
    )


class FakeCommunicate:
    def __init__(self, text, voice):
        self.text = text
        self.voice = voice

    async def save(self, path):  # writes a real 1-second WAV
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(b"\x00\x00" * 8000)


def make_generator(voice=None):
    seen = {"texts": [], "voices": []}

    def factory(text, voice):
        seen["texts"].append(text)
        seen["voices"].append(voice)
        return FakeCommunicate(text, voice)

    generator = VoiceoverGenerator() if voice is None else VoiceoverGenerator(voice=voice)
    generator.communicate = factory
    return generator, seen


def test_default_voice_is_natural_educational():
    assert DEFAULT_VOICE
    assert "Neural" in DEFAULT_VOICE or "Natural" in DEFAULT_VOICE


def test_chunks_respect_sentence_boundaries():
    narration = "First sentence. Second sentence! Third sentence? Fourth."
    chunks = _chunk_narration(narration)
    assert len(chunks) >= 1
    for chunk in chunks:
        assert not chunk.startswith(" ") and not chunk.endswith(" ")


def test_long_narration_chunked_without_losing_text(tmp_path):
    narration = " ".join(f"This is sentence number {i} with more than enough words to fill a chunk." for i in range(300))
    generator, seen = make_generator()
    generator.generate(make_scene(narration), str(tmp_path / "long.wav"))
    assert len(seen["texts"]) > 1
    rebuilt = " ".join(seen["texts"])
    assert rebuilt.split() == narration.split()


def test_generate_writes_audio_file_with_duration_and_format(tmp_path):
    generator, _ = make_generator()
    out = tmp_path / "voiceover.wav"
    result = generator.generate(make_scene("word " * 200), str(out))
    assert isinstance(result, VoiceoverResult)
    assert out.exists()
    assert result.path == out
    assert result.duration == pytest.approx(1.0, abs=0.05)
    assert result.voice == DEFAULT_VOICE


def test_multi_chunk_concatenates_durations(tmp_path):
    narration = " ".join(f"Another padded sentence number {i}." for i in range(120))
    generator, seen = make_generator()
    result = generator.generate(make_scene(narration), str(tmp_path / "multi.wav"))
    assert len(seen["texts"]) > 1, "expected narration to span multiple chunks"
    assert result.duration == pytest.approx(len(seen["texts"]), abs=0.1)


def test_generate_uses_requested_voice(tmp_path):
    generator, seen = make_generator(voice="en-GB-RyanNeural")
    generator.generate(make_scene(), str(tmp_path / "v1.wav"))
    assert seen["voices"][0] == "en-GB-RyanNeural"


def test_generate_raises_on_empty_narration(tmp_path):
    generator, _ = make_generator()
    with pytest.raises(ValueError):
        generator.generate(make_scene("   "), str(tmp_path / "e.wav"))


def test_generate_overrides_voice_per_call(tmp_path):
    generator, seen = make_generator()
    generator.generate(make_scene(), str(tmp_path / "v2.wav"), voice="en-US-EmmaMultilingualV2Neural")
    assert seen["voices"][0] == "en-US-EmmaMultilingualV2Neural"
