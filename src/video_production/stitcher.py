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

        if len(scene_paths) < 2:
            raise ValueError("need at least two scenes to stitch a mid-form video")

        clips = []
        composite = None
        try:
            for scene in scene_paths:
                path = Path(scene)
                if not path.exists():
                    raise FileNotFoundError(f"scene video not found: {path}")
                clips.append(VideoFileClip(str(path)))

            for clip in clips:
                if tuple(clip.size) != (width, height):
                    raise ValueError(
                        f"scene size {clip.size} does not match target {(width, height)}"
                    )

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
