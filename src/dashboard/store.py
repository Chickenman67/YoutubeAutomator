import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from werkzeug.utils import secure_filename


@dataclass
class VideoSummary:
    video_id: str
    topic: str
    title: str
    thumbnail: str

    def to_dict(self) -> Dict:
        return {
            "video_id": self.video_id,
            "topic": self.topic,
            "title": self.title,
            "thumbnail": self.thumbnail,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class VideoPackage:
    video_id: str
    directory: Path
    topic: str
    metadata: Dict
    fact_check: Dict
    script: Dict
    assets: Dict

    def to_dict(self) -> Dict:
        return {
            "video_id": self.video_id,
            "topic": self.topic,
            "metadata": self.metadata,
            "fact_check": self.fact_check,
            "script": self.script,
            "assets": self.assets,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class DashboardStore:
    def __init__(self, queue_root: str = "queue"):
        self.root = Path(queue_root)
        self.logger = logging.getLogger(__name__)

    @property
    def pending_dir(self) -> Path:
        return self.root / "pending_review"

    def list_pending(self) -> List[VideoSummary]:
        pending = self.pending_dir
        if not pending.is_dir():
            return []
        videos = []
        for folder in sorted(pending.iterdir()):
            if not folder.is_dir():
                continue
            master = folder / "metadata.json"
            if not master.exists():
                continue
            data = json.loads(master.read_text(encoding="utf-8"))
            videos.append(
                VideoSummary(
                    video_id=data["video_id"],
                    topic=data.get("topic", ""),
                    title=data.get("metadata", {}).get("title", ""),
                    thumbnail=data.get("assets", {}).get("thumbnail", ""),
                )
            )
        return videos

    def get_video(self, video_id: str) -> VideoPackage:
        folder = self.pending_dir / video_id
        if not folder.is_dir():
            raise FileNotFoundError(f"video not found: {video_id}")
        master = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        script_file = folder / f"{video_id}_script.json"
        script = (
            json.loads(script_file.read_text(encoding="utf-8"))
            if script_file.exists()
            else {}
        )
        return VideoPackage(
            video_id=video_id,
            directory=folder,
            topic=master.get("topic", ""),
            metadata=master.get("metadata", {}),
            fact_check=master.get("fact_check", {}),
            script=script,
            assets=master.get("assets", {}),
        )

    def approve(self, video_id: str) -> Path:
        return self._move(video_id, self.root / "approved")

    def reject(self, video_id: str) -> Path:
        return self._move(video_id, self.root / "rejected")

    def _move(self, video_id: str, target: Path) -> Path:
        source = self.pending_dir / video_id
        if not source.is_dir():
            raise FileNotFoundError(f"video not found: {video_id}")
        dest = target / video_id
        dest.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            shutil.move(str(item), str(dest / secure_filename(item.name)))
        source.rmdir()
        self.logger.info("moved video %s to %s", video_id, dest)
        return dest
