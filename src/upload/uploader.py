import json
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from googleapiclient.http import MediaFileUpload

from upload.quota import QuotaExceededError, QuotaTracker

UPLOADED = "uploaded"
FAILED = "failed"
SKIPPED = "skipped"

TRANSIENT_STATUS = (429, 500, 502, 503, 504)
QUOTA_REASONS = ("quotaExceeded", "dailyLimitExceeded")


class UploadError(Exception):
    pass


@dataclass
class UploadResult:
    video_id: str
    status: str
    youtube_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "video_id": self.video_id,
            "status": self.status,
            "youtube_id": self.youtube_id,
            "error": self.error,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def default_media_factory(path: str) -> MediaFileUpload:
    return MediaFileUpload(path, chunksize=-1, resumable=False)


class YouTubeUploader:
    def __init__(
        self,
        queue_root: str = "queue",
        client=None,
        quota: Optional[QuotaTracker] = None,
        privacy: str = "public",
        category_id: int = 27,
        retries: int = 3,
        upload_cost: int = 1600,
        media_factory: Optional[Callable[[str], object]] = None,
        sleep: Optional[Callable[[float], None]] = None,
    ):
        self.root = Path(queue_root)
        self.approved_dir = self.root / "approved"
        self.uploaded_dir = self.root / "uploaded"
        self.client = client
        self.quota = quota or QuotaTracker()
        self.privacy = privacy
        self.category_id = category_id
        self.retries = max(1, retries)
        self.upload_cost = upload_cost
        self.media_factory = media_factory or default_media_factory
        self.sleep = sleep or time.sleep
        self.logger = logging.getLogger(__name__)

    def upload_folder(self, folder: Path) -> UploadResult:
        video_id = folder.name
        try:
            master = json.loads(
                (folder / "metadata.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            return UploadResult(
                video_id=video_id, status=FAILED, error=f"invalid metadata: {exc}"
            )

        metadata = master.get("metadata", {})
        video_name = master.get("assets", {}).get("midform") or f"{video_id}_midform.mp4"
        video_file = folder / video_name
        if not video_file.is_file():
            return UploadResult(
                video_id=video_id, status=FAILED, error="midform asset missing"
            )

        if self.quota.remaining() < self.upload_cost:
            return UploadResult(
                video_id=video_id, status=SKIPPED, error="quota exhausted"
            )

        try:
            youtube_id = self._upload_video(video_id, video_file, metadata)
            self.quota.record(self.upload_cost)
        except QuotaExceededError as exc:
            self.logger.warning("quota exhausted uploading %s", video_id)
            return UploadResult(
                video_id=video_id, status=SKIPPED, error="quota exhausted"
            )
        except UploadError as exc:
            self.logger.error("upload failed for %s: %s", video_id, exc)
            return UploadResult(video_id=video_id, status=FAILED, error=str(exc))

        dest = self.uploaded_dir / video_id
        self.uploaded_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(folder), str(dest))
        self.logger.info("uploaded %s as %s", video_id, youtube_id)
        return UploadResult(
            video_id=video_id, status=UPLOADED, youtube_id=youtube_id
        )

    def _upload_video(self, video_id: str, video_file: Path, metadata: Dict) -> str:
        body = {
            "snippet": {
                "title": metadata.get("title", video_id),
                "description": metadata.get("description", ""),
                "tags": metadata.get("tags", []),
                "categoryId": str(metadata.get("category", self.category_id)),
            },
            "status": {"privacyStatus": self.privacy},
        }
        request = self.client.videos().insert(
            part="snippet,status",
            body=body,
            media_body=self.media_factory(str(video_file)),
        )
        response = self._execute_with_retry(request)
        return response["id"]

    def _execute_with_retry(self, request) -> Dict:
        for attempt in range(1, self.retries + 1):
            try:
                return request.execute()
            except Exception as exc:
                kind = self._error_kind(exc)
                if kind == "quota":
                    raise QuotaExceededError("quota exhausted") from exc
                if kind != "transient":
                    raise UploadError(str(exc)) from exc
                if attempt == self.retries:
                    raise UploadError(
                        f"upload failed after {self.retries} attempts: {exc}"
                    ) from exc
                self.logger.warning(
                    "transient error uploading (attempt %d/%d): %s",
                    attempt, self.retries, exc,
                )
                self.sleep(attempt)

    def _error_kind(self, exc) -> str:
        status = getattr(exc, "status", None)
        if status is None:
            resp = getattr(exc, "resp", None)
            status = getattr(resp, "status", None)
        reason = getattr(exc, "reason", None)
        if reason is None:
            details = getattr(exc, "error_details", None)
            if isinstance(details, list) and details:
                reason = details[0].get("reason")
        if status == 403 and reason in QUOTA_REASONS:
            return "quota"
        if status in TRANSIENT_STATUS or reason == "rateLimitExceeded":
            return "transient"
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return "transient"
        return "fatal"
