import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from fact_check.fact_checker import FactCheckReport
from metadata.generator import Metadata
from script_generation.schema import Script


@dataclass
class StagingManifest:
    video_id: str
    directory: Path
    midform: Path
    shorts: List[Path]
    thumbnail: Path
    metadata: Path
    fact_check: Path
    script: Path

    @property
    def assets(self) -> List[Path]:
        return [
            self.midform,
            *self.shorts,
            self.thumbnail,
            self.metadata,
            self.fact_check,
            self.script,
        ]


class StagingCollector:
    def __init__(self, staging_dir: str = "queue/staging"):
        self.staging_dir = Path(staging_dir)

    def collect(
        self,
        video_id: str,
        script: Script,
        fact_check: FactCheckReport,
        metadata: Metadata,
        midform_path: str,
        short_paths: List[str],
        thumbnail_path: str,
        staging_dir: Optional[str] = None,
    ) -> StagingManifest:
        if not video_id:
            raise ValueError("video_id is required")
        if script is None or fact_check is None or metadata is None:
            raise ValueError("script, fact_check, and metadata are required")
        if len(short_paths) != len(script.scenes):
            raise ValueError(
                f"expected {len(script.scenes)} short videos, got {len(short_paths)}"
            )
        for path in [midform_path, *short_paths, thumbnail_path]:
            if not Path(path).exists():
                raise FileNotFoundError(f"video asset not found: {path}")

        base = Path(staging_dir) if staging_dir else self.staging_dir
        directory = base / video_id
        midform = directory / f"{video_id}_midform.mp4"
        shorts = [
            directory / f"{video_id}_short_{i:02d}.mp4"
            for i in range(1, len(short_paths) + 1)
        ]
        thumbnail = directory / f"{video_id}_thumbnail.png"
        metadata_file = directory / f"{video_id}_metadata.json"
        fact_check_file = directory / f"{video_id}_fact_check.json"
        script_file = directory / f"{video_id}_script.json"

        directory.mkdir(parents=True, exist_ok=True)
        for source, dest in zip(
            [midform_path, *short_paths, thumbnail_path], [midform, *shorts, thumbnail]
        ):
            shutil.copy2(source, dest)
        metadata_file.write_text(metadata.to_json(), encoding="utf-8")
        fact_check_file.write_text(fact_check.to_json(), encoding="utf-8")
        script_file.write_text(script.to_json(), encoding="utf-8")

        return StagingManifest(
            video_id=video_id,
            directory=directory,
            midform=midform,
            shorts=shorts,
            thumbnail=thumbnail,
            metadata=metadata_file,
            fact_check=fact_check_file,
            script=script_file,
        )
