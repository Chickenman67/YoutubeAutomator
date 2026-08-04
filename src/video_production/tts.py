import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional

from script_generation.schema import Scene

DEFAULT_VOICE = "en-US-JennyNeural"
MAX_CHUNK_CHARS = 1500
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class VoiceoverResult:
    path: Path
    duration: float
    voice: str


def probe_audio_duration(path: str) -> float:
    from moviepy import AudioFileClip

    with AudioFileClip(str(path)) as audio:
        return float(audio.duration)


def _default_communicate(text: str, voice: str) -> Any:
    from edge_tts import Communicate

    return Communicate(text, voice)


def _chunk_narration(narration: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    sentences = [s for s in _SENTENCE_SPLIT.split(narration.strip()) if s]
    if not sentences:
        return [narration]
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        candidate = (current + " " + sentence).strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _codec_for(suffix: str) -> str:
    if suffix == ".mp3":
        return "libmp3lame"
    if suffix == ".wav":
        return "pcm_s16le"
    raise ValueError(f"Unsupported audio format '{suffix}' (expected .mp3 or .wav)")


class VoiceoverGenerator:
    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        communicate: Optional[Callable[[str, str], Any]] = None,
    ):
        self.voice = voice
        self.communicate = communicate or _default_communicate

    @staticmethod
    def _concat(audio_parts: List[Path], output_path: Path, codec: str) -> None:
        from moviepy import AudioFileClip, concatenate_audioclips

        clips = [AudioFileClip(str(part)) for part in audio_parts]
        try:
            combined = concatenate_audioclips(clips) if len(clips) > 1 else clips[0]
            combined.write_audiofile(str(output_path), fps=44100, codec=codec, logger=None)
        finally:
            for clip in clips:
                clip.close()

    def generate(
        self,
        scene: Scene,
        output_path: str,
        voice: Optional[str] = None,
    ) -> VoiceoverResult:
        narration = scene.narration.strip()
        if not narration:
            raise ValueError("Scene narration is empty; nothing to speak.")

        voice = voice or self.voice
        out = Path(output_path)
        codec = _codec_for(out.suffix.lower())

        parts: List[Path] = []
        try:
            for i, chunk in enumerate(_chunk_narration(narration)):
                part = out.with_name(f"{out.stem}.part{i}.mp3")
                communicator = self.communicate(chunk, voice)
                asyncio.run(communicator.save(str(part)))
                parts.append(part)
            self._concat(parts, out, codec)
        finally:
            for part in parts:
                part.unlink(missing_ok=True)

        return VoiceoverResult(path=out, duration=probe_audio_duration(out), voice=voice)
