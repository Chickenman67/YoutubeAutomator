import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from upload.quota import QuotaTracker
from upload.uploader import YouTubeUploader, default_media_factory


class FakeHttpError(Exception):
    def __init__(self, status, reason=None):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.reason = reason


class FakeRequest:
    def __init__(self, client):
        self._client = client

    def execute(self):
        self._client.executes += 1
        item = self._client._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, *responses):
        self.calls = []
        self.executes = 0
        self._responses = list(responses)

    def videos(self):
        return self

    def insert(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRequest(self)


class FakeMedia:
    def __init__(self, path):
        self.path = path


def fake_media_factory(path):
    return FakeMedia(path)


def seed_approved(queue_root, video_id="vid-1", topic="Space", assets=True):
    folder = queue_root / "approved" / video_id
    folder.mkdir(parents=True, exist_ok=True)
    master = {
        "video_id": video_id,
        "topic": topic,
        "metadata": {
            "title": f"{topic} Explained",
            "description": "desc",
            "tags": ["tag1", "tag2"],
        },
        "assets": {"midform": f"{video_id}_midform.mp4"} if assets else {},
    }
    (folder / "metadata.json").write_text(json.dumps(master), encoding="utf-8")
    if assets:
        (folder / f"{video_id}_midform.mp4").write_bytes(b"video")
    return folder


def make_uploader(tmp_path, queue_root, client, **kwargs):
    kwargs.setdefault("quota", QuotaTracker(quota_path=str(tmp_path / "quota.json")))
    kwargs.setdefault("media_factory", fake_media_factory)
    kwargs.setdefault("sleep", lambda _: None)
    return YouTubeUploader(queue_root=str(queue_root), client=client, **kwargs)


def test_upload_sends_metadata_and_privacy(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    client = FakeClient({"id": "y1"})
    uploader = make_uploader(tmp_path, queue_root, client)
    result = uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert result.status == "uploaded"
    assert result.youtube_id == "y1"
    call = client.calls[0]
    assert call["part"] == "snippet,status"
    body = call["body"]
    assert body["snippet"]["title"] == "Space Explained"
    assert body["snippet"]["description"] == "desc"
    assert body["snippet"]["tags"] == ["tag1", "tag2"]
    assert body["snippet"]["categoryId"] == "27"
    assert body["status"]["privacyStatus"] == "public"
    assert call["media_body"].path.endswith("vid-1_midform.mp4")


def test_upload_uses_custom_privacy_and_category(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    client = FakeClient({"id": "y1"})
    uploader = make_uploader(tmp_path, queue_root, client, privacy="unlisted", category_id=22)
    uploader.upload_folder(queue_root / "approved" / "vid-1")
    body = client.calls[0]["body"]
    assert body["status"]["privacyStatus"] == "unlisted"
    assert body["snippet"]["categoryId"] == "22"


def test_upload_moves_folder_to_uploaded(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    client = FakeClient({"id": "y1"})
    uploader = make_uploader(tmp_path, queue_root, client)
    uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert not (queue_root / "approved" / "vid-1").exists()
    assert (queue_root / "uploaded" / "vid-1").is_dir()
    assert (queue_root / "uploaded" / "vid-1" / "metadata.json").exists()


def test_upload_records_quota_cost(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    client = FakeClient({"id": "y1"})
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"))
    uploader = make_uploader(tmp_path, queue_root, client, quota=tracker)
    uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert tracker.used() == 1600


def test_upload_missing_metadata_fails(tmp_path):
    queue_root = tmp_path / "queue"
    folder = queue_root / "approved" / "bad"
    folder.mkdir(parents=True)
    client = FakeClient()
    uploader = make_uploader(tmp_path, queue_root, client)
    result = uploader.upload_folder(folder)
    assert result.status == "failed"
    assert "metadata" in result.error
    assert client.calls == []


def test_upload_missing_midform_fails(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root, assets=False)
    client = FakeClient()
    uploader = make_uploader(tmp_path, queue_root, client)
    result = uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert result.status == "failed"
    assert "midform" in result.error
    assert client.calls == []


def test_upload_retries_on_transient_error(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    client = FakeClient(FakeHttpError(503), FakeHttpError(503), {"id": "y1"})
    uploader = make_uploader(tmp_path, queue_root, client, retries=3)
    result = uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert result.status == "uploaded"
    assert len(client.calls) == 1
    assert client.executes == 3


def test_upload_retries_on_connection_error(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    client = FakeClient(ConnectionError("boom"), {"id": "y1"})
    uploader = make_uploader(tmp_path, queue_root, client, retries=3)
    result = uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert result.status == "uploaded"
    assert client.executes == 2


def test_upload_fails_after_retries_exhausted(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    client = FakeClient(FakeHttpError(503), FakeHttpError(503), FakeHttpError(503))
    uploader = make_uploader(tmp_path, queue_root, client, retries=3)
    result = uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert result.status == "failed"
    assert "3 attempts" in result.error
    assert client.executes == 3
    assert not (queue_root / "uploaded" / "vid-1").exists()


def test_upload_fatal_error_does_not_retry(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    client = FakeClient(FakeHttpError(400))
    uploader = make_uploader(tmp_path, queue_root, client, retries=3)
    result = uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert result.status == "failed"
    assert client.executes == 1


def test_api_quota_exceeded_marks_skipped(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    client = FakeClient(FakeHttpError(403, reason="quotaExceeded"))
    uploader = make_uploader(tmp_path, queue_root, client)
    result = uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert result.status == "skipped"
    assert result.error == "quota exhausted"
    assert client.executes == 1
    assert not (queue_root / "uploaded" / "vid-1").exists()


def test_pre_check_quota_exhausted_marks_skipped_without_calling(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    client = FakeClient()
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"), daily_limit=1600)
    tracker.record(1600)
    uploader = make_uploader(tmp_path, queue_root, client, quota=tracker)
    result = uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert result.status == "skipped"
    assert result.error == "quota exhausted"
    assert client.calls == []


def test_upload_uses_video_id_as_title_fallback(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root)
    master = json.loads(
        (queue_root / "approved" / "vid-1" / "metadata.json").read_text(encoding="utf-8")
    )
    del master["metadata"]["title"]
    (queue_root / "approved" / "vid-1" / "metadata.json").write_text(
        json.dumps(master), encoding="utf-8"
    )
    client = FakeClient({"id": "y1"})
    uploader = make_uploader(tmp_path, queue_root, client)
    uploader.upload_folder(queue_root / "approved" / "vid-1")
    assert client.calls[0]["body"]["snippet"]["title"] == "vid-1"


def test_default_media_factory_returns_media_upload(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")
    from googleapiclient.http import MediaFileUpload
    media = default_media_factory(str(video))
    assert isinstance(media, MediaFileUpload)

from upload.uploader import BatchUploadResult, UploadResult


def test_upload_batch_uploads_all_approved(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root, video_id="vid-1")
    seed_approved(queue_root, video_id="vid-2")
    client = FakeClient({"id": "y1"}, {"id": "y2"})
    uploader = make_uploader(tmp_path, queue_root, client)
    batch = uploader.upload_batch()
    assert [r.video_id for r in batch.succeeded] == ["vid-1", "vid-2"]
    assert batch.failed == []
    assert (queue_root / "uploaded" / "vid-1").is_dir()
    assert (queue_root / "uploaded" / "vid-2").is_dir()
    assert not (queue_root / "approved" / "vid-1").exists()
    assert not (queue_root / "approved" / "vid-2").exists()


def test_upload_batch_empty_approved_dir(tmp_path):
    queue_root = tmp_path / "queue"
    (queue_root / "approved").mkdir(parents=True)
    client = FakeClient()
    uploader = make_uploader(tmp_path, queue_root, client)
    batch = uploader.upload_batch()
    assert batch.succeeded == []
    assert batch.failed == []
    assert batch.skipped == []


def test_upload_batch_skips_non_dirs(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root, video_id="vid-1")
    stray = queue_root / "approved" / "notes.txt"
    stray.write_text("not a folder")
    client = FakeClient({"id": "y1"})
    uploader = make_uploader(tmp_path, queue_root, client)
    batch = uploader.upload_batch()
    assert [r.video_id for r in batch.succeeded] == ["vid-1"]


def test_quota_exhausted_skips_and_stops_batch(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root, video_id="vid-1")
    seed_approved(queue_root, video_id="vid-2")
    client = FakeClient()
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"), daily_limit=1600)
    tracker.record(1600)
    uploader = make_uploader(tmp_path, queue_root, client, quota=tracker)
    batch = uploader.upload_batch()
    assert [r.video_id for r in batch.skipped] == ["vid-1"]
    assert client.calls == []
    assert (queue_root / "approved" / "vid-2").is_dir()


def test_batch_result_keeps_failures(tmp_path):
    queue_root = tmp_path / "queue"
    seed_approved(queue_root, video_id="vid-ok")
    seed_approved(queue_root, video_id="vid-bad", assets=False)
    client = FakeClient({"id": "y1"})
    uploader = make_uploader(tmp_path, queue_root, client)
    batch = uploader.upload_batch()
    assert [r.video_id for r in batch.succeeded] == ["vid-ok"]
    assert [r.video_id for r in batch.failed] == ["vid-bad"]
    assert (queue_root / "uploaded" / "vid-ok").is_dir()
    assert (queue_root / "approved" / "vid-bad").is_dir()


def test_batch_result_to_dict():
    batch = BatchUploadResult(
        results=[
            UploadResult(video_id="a", status="uploaded", youtube_id="y"),
            UploadResult(video_id="b", status="failed", error="boom"),
            UploadResult(video_id="c", status="skipped", error="quota exhausted"),
        ]
    )
    data = batch.to_dict()
    assert [r["video_id"] for r in data["succeeded"]] == ["a"]
    assert [r["video_id"] for r in data["failed"]] == ["b"]
    assert [r["video_id"] for r in data["skipped"]] == ["c"]
    assert data["succeeded"][0]["youtube_id"] == "y"
    assert data["failed"][0]["error"] == "boom"
