import json
import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pipeline.staging import StagingManifest


def generate_video_id(now: Optional[datetime] = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


@dataclass
class ExportResult:
    video_id: str
    directory: Path
    assets: List[Path]
    metadata: Path

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "directory": str(self.directory),
            "assets": [str(p) for p in self.assets],
            "metadata": str(self.metadata),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class QueueExporter:
    def __init__(self, pending_dir: str = "queue/pending_review"):
        self.pending_dir = Path(pending_dir)
        self.logger = logging.getLogger(__name__)

    def export(
        self,
        manifest: StagingManifest,
        pending_dir: Optional[str] = None,
        video_id: Optional[str] = None,
    ) -> ExportResult:
        base = Path(pending_dir) if pending_dir else self.pending_dir
        vid = video_id or manifest.video_id or generate_video_id()
        dest = base / vid
        dest.mkdir(parents=True, exist_ok=True)

        assets = []
        for asset in manifest.assets:
            copied = dest / asset.name
            shutil.copy2(asset, copied)
            assets.append(copied)

        master = dest / "metadata.json"
        master.write_text(self._build_master(manifest, vid), encoding="utf-8")
        self.logger.info("exported video %s to %s", vid, dest)
        return ExportResult(video_id=vid, directory=dest, assets=assets, metadata=master)

    def _build_master(self, manifest: StagingManifest, video_id: str) -> str:
        script = json.loads(manifest.script_file.read_text(encoding="utf-8"))
        metadata = json.loads(manifest.metadata_file.read_text(encoding="utf-8"))
        fact_check = json.loads(manifest.fact_check_file.read_text(encoding="utf-8"))
        master = {
            "video_id": video_id,
            "topic": script.get("topic") or fact_check.get("topic") or "",
            "metadata": metadata,
            "fact_check": fact_check,
            "assets": {
                "midform": manifest.midform.name,
                "shorts": [p.name for p in manifest.shorts],
                "thumbnail": manifest.thumbnail.name,
            },
        }
        return json.dumps(master, indent=2)
