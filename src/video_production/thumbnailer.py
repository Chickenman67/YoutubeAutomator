from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]


def _default_font_path() -> Optional[str]:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


@dataclass
class ThumbnailResult:
    path: Path
    width: int
    height: int
    source_path: Path
    frame_time: float
    title: str


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
        from moviepy import VideoFileClip

        width = width or self.width
        height = height or self.height

        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"mid-form video not found: {path}")

        with VideoFileClip(str(path)) as clip:
            duration = float(clip.duration)
            frame_time = min(float(frame_time), max(0.0, duration - 0.05))
            frame = clip.get_frame(frame_time)

        img = Image.fromarray(frame).convert("RGB")
        img = img.resize((width, height), Image.LANCZOS)

        if title.strip():
            self._draw_title(img, title, font_path)

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, format="PNG")

        return ThumbnailResult(
            path=out,
            width=width,
            height=height,
            source_path=path,
            frame_time=float(frame_time),
            title=title,
        )

    def _resolve_font(self, size: int, font_path: Optional[str]) -> ImageFont:
        resolved = font_path or _default_font_path()
        if resolved:
            return ImageFont.truetype(resolved, size)
        return ImageFont.load_default(size=size)

    @staticmethod
    def _wrap(text: str, font: ImageFont, max_width: float) -> list[str]:
        lines: list[str] = []
        current: list[str] = []
        for word in text.split():
            candidate = " ".join(current + [word])
            if current and font.getlength(candidate) > max_width:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))
        return lines or [""]

    def _draw_title(self, img: Image.Image, title: str, font_path: Optional[str]):
        width, height = img.size
        margin = int(width * 0.05)
        max_text_width = width - 2 * margin
        max_band_height = int(height * 0.30)

        font_size = int(height * 0.14)
        font = None
        lines = []
        while font_size >= 20:
            font = self._resolve_font(font_size, font_path)
            lines = self._wrap(title, font, max_text_width)
            if len(lines) * int(font_size * 1.3) <= max_band_height:
                break
            font_size -= 8
        if font is None:
            font = self._resolve_font(20, font_path)
            lines = self._wrap(title, font, max_text_width)

        line_height = int(font_size * 1.3)
        padding = int(font_size * 0.35)
        text_height = len(lines) * line_height
        band_top = height - margin - text_height - 2 * padding
        band_bottom = height - margin

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rounded_rectangle(
            [margin, band_top, width - margin, band_bottom],
            radius=padding,
            fill=(0, 0, 0, 180),
        )

        y = band_top + padding
        for line in lines:
            text_width = font.getlength(line)
            x = (width - text_width) / 2
            draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 230))
            draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
            y += line_height

        img.paste(overlay, (0, 0), overlay)
