import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from script_generation.schema import Scene


@dataclass
class RenderResult:
    path: Path
    width: int
    height: int
    duration: float
    source_path: Path


class SceneRenderer:
    def __init__(
        self,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        wpm: int = 150,
        min_duration: float = 60.0,
        max_duration: float = 90.0,
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.wpm = wpm
        self.min_duration = min_duration
        self.max_duration = max_duration

    def estimate_duration(self, narration: str) -> float:
        words = len(narration.split())
        return (words / max(self.wpm, 1)) * 60.0

    def resolve_duration(self, narration: str, explicit: Optional[float] = None) -> float:
        if explicit is not None:
            return float(explicit)
        estimated = self.estimate_duration(narration)
        return max(self.min_duration, min(self.max_duration, estimated))

    def generate_source(self, scene: Scene, duration: float) -> str:
        src_path = str(Path(__file__).parent.parent)
        keywords = list(scene.key_visual_keywords or [])
        return f"""import sys
sys.path.insert(0, {src_path!r})

from manim import *

from video_production.stickfigures import ACCENT_COLOR, build_keyword_visual


class StickFigureScene(Scene):
    def construct(self):
        keywords = {keywords!r}
        total = {float(duration)!r}
        if not keywords:
            keywords = ["educational visual"]
        n = float(len(keywords))
        slice_len = total / n if n else 1.0
        for kw in keywords:
            visual = build_keyword_visual(kw, color=WHITE, accent=ACCENT_COLOR)
            self.play(FadeIn(visual), run_time=min(0.5, slice_len * 0.5))
            self.wait(max(0.2, slice_len * 0.5))
"""

    @staticmethod
    def _find_output(media_dir: Path, output_name: str) -> Path:
        hits = list(Path(media_dir).rglob(f"**/{output_name}.mp4"))
        if not hits:
            raise FileNotFoundError(f"Manim did not produce {output_name}.mp4 under {media_dir}")
        return max(hits, key=lambda p: p.stat().st_mtime)

    @staticmethod
    def _probe(path: Path):
        from moviepy import VideoFileClip

        with VideoFileClip(str(path)) as clip:
            width, height = clip.size
            return int(width), int(height), float(clip.duration)

    def render(
        self,
        scene: Scene,
        output_name: str,
        output_dir: str,
        duration: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
        python: Optional[str] = None,
    ) -> RenderResult:
        duration = self.resolve_duration(scene.narration, duration)
        width = width or self.width
        height = height or self.height
        fps = fps or self.fps

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        source = self.generate_source(scene, duration)
        source_path = out_dir / f"{output_name}.py"
        source_path.write_text(source, encoding="utf-8")

        media_dir = out_dir / "media"
        cmd = [
            python or sys.executable,
            "-m", "manim", "render",
            str(source_path),
            "StickFigureScene",
            "-r", f"{width},{height}",
            "--fps", str(fps),
            "--media_dir", str(media_dir),
            "-o", output_name,
            "--format", "mp4",
            "--disable_caching",
            "--verbosity", "warning",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=str(out_dir))
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip().splitlines()[-8:]
            raise RuntimeError(
                f"Manim render failed (exit {exc.returncode}). "
                f"Generated source: {source_path}. {detail}"
            ) from exc

        produced = self._find_output(media_dir, output_name)
        pwidth, pheight, pduration = self._probe(produced)
        return RenderResult(
            path=produced,
            width=pwidth,
            height=pheight,
            duration=pduration,
            source_path=source_path,
        )
