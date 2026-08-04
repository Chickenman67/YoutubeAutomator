from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class AssemblyResult:
    path: Path
    width: int
    height: int
    duration: float
    has_audio: bool


def _fit_to(clip, width: int, height: int):
    src_width, src_height = clip.size
    scale = max(width / src_width, height / src_height)
    scaled = clip.resized(new_size=(round(src_width * scale), round(src_height * scale)))
    tw, th = scaled.size
    x1 = max(0, (tw - width) // 2)
    y1 = max(0, (th - height) // 2)
    return scaled.cropped(x1=x1, y1=y1, x2=x1 + width, y2=y1 + height)


class SceneAssembler:
    def __init__(self, width: int = 1080, height: int = 1920, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps

    def assemble(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
    ) -> AssemblyResult:
        from moviepy import AudioFileClip, VideoFileClip, vfx

        width = width or self.width
        height = height or self.height
        fps = fps or self.fps

        video = VideoFileClip(video_path)
        audio = AudioFileClip(audio_path)
        try:
            target = audio.duration
            fitted = _fit_to(video, width, height)
            if fitted.duration < target - 0.05:
                fitted = fitted.with_effects(
                    [vfx.Freeze(t="end", total_duration=target)]
                )
            elif fitted.duration > target + 0.05:
                fitted = fitted.subclipped(0, target)

            clip = fitted.with_audio(audio)
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            clip.write_videofile(
                str(out), fps=int(fps), codec="libx264", audio_codec="aac", logger=None
            )
        finally:
            audio.close()
            video.close()

        with VideoFileClip(str(out)) as final:
            out_width, out_height = final.size
            return AssemblyResult(
                path=out,
                width=int(out_width),
                height=int(out_height),
                duration=float(final.duration),
                has_audio=final.audio is not None,
            )
