# YouTube Upload Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each task below. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `src/upload/` so approved Videos in `queue/approved/` are uploaded to YouTube via the Data API v3 with OAuth 2.0 auth, tracked daily quota, retry logic, and a move to `queue/uploaded/` on success.

**Architecture:** Three small modules under `src/upload/`. `quota.py` owns a `QuotaTracker` that persists daily quota usage to a JSON file. `auth.py` owns OAuth credential load/save/one-time browser flow plus a `build_client` seam for constructing the YouTube service. `uploader.py` owns the batch orchestration: `YouTubeUploader` walks `queue/approved/`, reads each master `metadata.json` (from #17), builds the `videos().insert` request with title/description/tags/category/privacy, executes with transient-error retries, records quota, and moves the folder to `queue/uploaded/`. The YouTube client, media factory, quota tracker, and sleep are all injected seams so every test is offline.

**Tech Stack:** Python 3.14, google-api-python-client 2.198.0 (youtube v3), google-auth-oauthlib 1.4.0, stdlib (`dataclasses`, `json`, `logging`, `shutil`, `pathlib`, `time`). pytest with plain stub fakes — no network, no real uploads.

**Design context:** Consumes the #17 folder layout (`queue/approved/{video_id}/metadata.json` with `{metadata: {title, description, tags}, assets: {midform}}`) produced by `src/pipeline/exporter.py` and moved by #18's dashboard approve flow. Glossary (`CONTEXT.md`): Queue states `pending_review/ → approved/ → uploaded/`. Settings (`config/settings.json` → `upload` block): `daily_quota_limit: 10000`, `upload_cost: 1600`, `default_privacy: "public"`, `retry_attempts: 3`, and `metadata.youtube_category_id: 27` (Education).

## Global Constraints

- Test runner: `venv\Scripts\python -m pytest -q` (full suite). For one file: `venv\Scripts\python -m pytest tests\test_uploader.py -v`.
- Repo test convention: `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))` at top of every test file; per-file helper duplication is the known self-contained-test convention.
- Follow repo conventions: dataclass result objects with `to_dict`/`to_json`, typed injected seams, `Path.mkdir(parents=True, exist_ok=True)`, `logging.getLogger(__name__)`, no comments in production code unless asked.
- Sibling imports are plain absolute from the `src` root (e.g. `from upload.quota import QuotaTracker`).
- Mock the YouTube client, the OAuth flow, and the media factory in every test — zero network calls, zero real uploads.
- Success moves a folder to `queue/uploaded/{video_id}/`; failures/skips never modify `queue/approved/`.
- Quota: 10k units/day, upload cost 1600, persisted to `config/quota.json` keyed by ISO date.
- Never log or commit real tokens/credentials. `config/youtube_token.json` and `config/quota.json` go in `.gitignore`.
- Wiring the `upload` subcommand in `src/__main__.py` is out of scope (dashboard precedent: #18/#19 left the CLI stub untouched).

---

### Task 1: Quota tracker

**Files:**
- Create: `src/upload/__init__.py`
- Create: `src/upload/quota.py`
- Create: `tests/test_quota.py`
- Modify: `.gitignore` (add token/quota ignores; keeps the pending `.playwright-mcp/` edit)

**Interfaces:**
- Produces: `QuotaTracker(quota_path="config/quota.json", daily_limit=10000)` with `used(day=None) -> int`, `remaining(day=None) -> int`, `record(cost, day=None) -> int`, and `QuotaExceededError`. `day` is a `datetime.date`; the default is today. Persistence file shape: `{"YYYY-MM-DD": used_units}`.

- [ ] **Step 1: Write the failing tests**

```python
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from upload.quota import QuotaExceededError, QuotaTracker


def test_new_tracker_starts_at_zero(tmp_path):
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"))
    assert tracker.used() == 0
    assert tracker.remaining() == 10000


def test_record_adds_cost_and_persists(tmp_path):
    path = tmp_path / "quota.json"
    tracker = QuotaTracker(quota_path=str(path))
    assert tracker.record(1600) == 1600
    reloaded = QuotaTracker(quota_path=str(path))
    assert reloaded.used() == 1600
    assert reloaded.remaining() == 8400


def test_record_accumulates_costs(tmp_path):
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"))
    tracker.record(1600)
    tracker.record(1600)
    assert tracker.used() == 3200


def test_record_raises_when_exceeding_limit(tmp_path):
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"), daily_limit=2000)
    tracker.record(1600)
    with pytest.raises(QuotaExceededError):
        tracker.record(1600)


def test_usage_is_per_day(tmp_path):
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"))
    tracker.record(1600, day=date(2026, 8, 1))
    assert tracker.used(date(2026, 8, 1)) == 1600
    assert tracker.used(date(2026, 8, 2)) == 0
    assert tracker.remaining(date(2026, 8, 2)) == 10000


def test_missing_or_corrupt_file_counts_as_zero(tmp_path):
    path = tmp_path / "quota.json"
    path.write_text("{not json", encoding="utf-8")
    tracker = QuotaTracker(quota_path=str(path))
    assert tracker.used() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_quota.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'upload.quota'`.

- [ ] **Step 3: Write minimal implementation**

`src/upload/__init__.py`:
```python
from .quota import QuotaExceededError, QuotaTracker

__all__ = ["QuotaExceededError", "QuotaTracker"]
```

`src/upload/quota.py`:
```python
import json
import logging
from datetime import date
from pathlib import Path


def daily_key(day=None) -> str:
    return (day or date.today()).isoformat()


class QuotaExceededError(Exception):
    pass


class QuotaTracker:
    def __init__(self, quota_path: str = "config/quota.json", daily_limit: int = 10000):
        self.quota_path = Path(quota_path)
        self.daily_limit = daily_limit
        self.logger = logging.getLogger(__name__)
        self._usage = self._load()

    def _load(self) -> dict:
        if not self.quota_path.is_file():
            return {}
        try:
            data = json.loads(self.quota_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def used(self, day=None) -> int:
        return int(self._usage.get(daily_key(day), 0))

    def remaining(self, day=None) -> int:
        return max(0, self.daily_limit - self.used(day))

    def record(self, cost: int, day=None) -> int:
        key = daily_key(day)
        new_total = self.used(day) + cost
        if new_total > self.daily_limit:
            raise QuotaExceededError(
                f"daily quota exceeded: {new_total} > {self.daily_limit}"
            )
        self._usage[key] = new_total
        self._save()
        self.logger.info("quota used today: %s", new_total)
        return new_total

    def _save(self):
        self.quota_path.parent.mkdir(parents=True, exist_ok=True)
        self.quota_path.write_text(json.dumps(self._usage, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_quota.py -v`
Expected: 6 passed.

- [ ] **Step 5: Update `.gitignore`**

Add below the existing `# Browser automation` block (keep the already-present `.playwright-mcp/` line):
```
# YouTube credentials and upload state
config/youtube_token.json
config/quota.json
```

- [ ] **Step 6: Commit**

```bash
git add src/upload/__init__.py src/upload/quota.py tests/test_quota.py .gitignore
git commit -m "Add daily quota tracker for YouTube uploads (#20)"
```

---

### Task 2: OAuth authentication and client building

**Files:**
- Create: `src/upload/auth.py`
- Create: `tests/test_auth.py`

**Interfaces:**
- Produces: `DEFAULT_SCOPES`, `AuthError`, `load_credentials(token_path, scopes=DEFAULT_SCOPES) -> Credentials`, `save_credentials(credentials, token_path) -> Path`, `run_auth_flow(token_path, client_id, client_secret, scopes=DEFAULT_SCOPES) -> Credentials`, `get_credentials(token_path, client_id="", client_secret="", scopes=DEFAULT_SCOPES) -> Credentials`, `build_client(credentials, builder=None)`.
- Consumes (Task 3): `build_client` for constructing the injected `client`; the uploader itself does not call auth functions.
- Note: the one-time browser flow runs only when no stored token exists; a stored token must contain a `refresh_token`.

- [ ] **Step 1: Write the failing tests**

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from google.oauth2.credentials import Credentials
from upload import auth as auth_module
from upload.auth import (
    AuthError, DEFAULT_SCOPES, build_client, get_credentials,
    load_credentials, run_auth_flow, save_credentials,
)


def token_json(refresh="refresh-1"):
    return {
        "client_id": "cid",
        "client_secret": "csecret",
        "refresh_token": refresh,
        "token": "tok",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def make_credentials():
    return Credentials(
        token="tok", refresh_token="refresh-1", client_id="cid",
        client_secret="csecret", token_uri="https://oauth2.googleapis.com/token",
    )


def test_load_credentials_reads_stored_refresh_token(tmp_path):
    path = tmp_path / "token.json"
    path.write_text(json.dumps(token_json()), encoding="utf-8")
    creds = load_credentials(str(path))
    assert isinstance(creds, Credentials)
    assert creds.refresh_token == "refresh-1"
    assert set(creds.scopes) == set(DEFAULT_SCOPES)


def test_load_credentials_raises_when_missing(tmp_path):
    with pytest.raises(AuthError):
        load_credentials(str(tmp_path / "nope.json"))


def test_load_credentials_raises_without_refresh_token(tmp_path):
    path = tmp_path / "token.json"
    path.write_text(json.dumps(token_json(refresh=None)), encoding="utf-8")
    with pytest.raises(AuthError):
        load_credentials(str(path))


def test_save_credentials_writes_token_file(tmp_path):
    path = save_credentials(make_credentials(), str(tmp_path / "nested" / "token.json"))
    assert path.is_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["refresh_token"] == "refresh-1"


def test_get_credentials_returns_stored_when_token_exists(tmp_path):
    path = tmp_path / "token.json"
    path.write_text(json.dumps(token_json()), encoding="utf-8")
    creds = get_credentials(str(path), "cid", "csecret")
    assert creds.refresh_token == "refresh-1"


def test_get_credentials_runs_flow_when_no_token(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    ran = {}

    def fake_run(token_path_arg, client_id, client_secret, scopes=None):
        ran["token_path"] = token_path_arg
        ran["client_id"] = client_id
        return make_credentials()

    monkeypatch.setattr(auth_module, "run_auth_flow", fake_run)
    creds = get_credentials(str(token_path), "cid", "csecret")
    assert creds.refresh_token == "refresh-1"
    assert ran["token_path"] == str(token_path)
    assert ran["client_id"] == "cid"


def test_run_auth_flow_requires_client_credentials(tmp_path):
    with pytest.raises(AuthError):
        run_auth_flow(str(tmp_path / "token.json"), "", "")


def test_run_auth_flow_runs_local_server_and_saves(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    captured = {}

    class FakeFlow:
        def run_local_server(self, prompt=None):
            captured["prompt"] = prompt
            return make_credentials()

    def fake_from_client_config(cls, client_config, scopes=None):
        captured["config"] = client_config
        captured["scopes"] = scopes
        return FakeFlow()

    monkeypatch.setattr(
        auth_module.InstalledAppFlow,
        "from_client_config",
        classmethod(fake_from_client_config),
    )
    creds = run_auth_flow(str(token_path), "cid", "csecret")
    assert creds.refresh_token == "refresh-1"
    assert captured["prompt"] == "consent"
    assert captured["config"]["installed"]["client_id"] == "cid"
    assert token_path.is_file()
```

Note: on Python 3.14, assigning a plain function to a class attribute no longer binds the class on class access (`type(A.fn)` is `function`, not `method`). Wrap the patched fake in `classmethod(...)` so the call `InstalledAppFlow.from_client_config(config, scopes=...)` dispatches with `cls` first.


def test_build_client_creates_youtube_v3():
    captured = {}
    creds = make_credentials()

    def fake_builder(name, version, credentials=None):
        captured["name"] = name
        captured["version"] = version
        captured["credentials"] = credentials
        return "service"

    assert build_client(creds, builder=fake_builder) == "service"
    assert captured == {"name": "youtube", "version": "v3", "credentials": creds}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'upload.auth'`.

- [ ] **Step 3: Write minimal implementation**

`src/upload/auth.py`:
```python
import json
import logging
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


class AuthError(Exception):
    pass


def load_credentials(token_path: str, scopes=DEFAULT_SCOPES) -> Credentials:
    path = Path(token_path)
    if not path.is_file():
        raise AuthError(f"no stored token at {token_path}")
    info = json.loads(path.read_text(encoding="utf-8"))
    if not info.get("refresh_token"):
        raise AuthError("stored token has no refresh token")
    return Credentials.from_authorized_user_info(info, scopes=scopes)


def save_credentials(credentials, token_path: str) -> Path:
    path = Path(token_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(credentials.to_json(), encoding="utf-8")
    return path


def _client_config(client_id: str, client_secret: str) -> dict:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }


def run_auth_flow(
    token_path: str, client_id: str, client_secret: str, scopes=DEFAULT_SCOPES
) -> Credentials:
    if not client_id or not client_secret:
        raise AuthError("YouTube client id/secret not configured")
    flow = InstalledAppFlow.from_client_config(
        _client_config(client_id, client_secret), scopes=scopes
    )
    credentials = flow.run_local_server(prompt="consent")
    save_credentials(credentials, token_path)
    return credentials


def get_credentials(
    token_path: str,
    client_id: str = "",
    client_secret: str = "",
    scopes=DEFAULT_SCOPES,
) -> Credentials:
    if Path(token_path).is_file():
        return load_credentials(token_path, scopes=scopes)
    return run_auth_flow(token_path, client_id, client_secret, scopes=scopes)


def build_client(credentials, builder=None):
    if builder is None:
        from googleapiclient.discovery import build as builder
    return builder("youtube", "v3", credentials=credentials)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_auth.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/upload/auth.py tests/test_auth.py
git commit -m "Add YouTube OAuth authentication and client building (#20)"
```

---

### Task 3: Single-folder upload with retry

**Files:**
- Create: `src/upload/uploader.py`
- Create: `tests/test_uploader.py`

**Interfaces:**
- Consumes: `QuotaTracker`, `QuotaExceededError` from Task 1. The injected `client` implements `videos().insert(part=..., body=..., media_body=...)` returning a request whose `.execute()` returns `{"id": ...}`.
- Produces: `UploadResult` (`video_id`, `status` in `"uploaded"|"failed"|"skipped"`, `youtube_id`, `error`), `UploadError`, `YouTubeUploader` with public `upload_folder(folder: Path) -> UploadResult`. Constants `UPLOADED`, `FAILED`, `SKIPPED`.
- `YouTubeUploader(queue_root="queue", client=None, quota=None, privacy="public", category_id=27, retries=3, upload_cost=1600, media_factory=None, sleep=None)`. `media_factory(path)` default `default_media_factory` (wraps `MediaFileUpload`); `sleep(seconds)` default `time.sleep`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_uploader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'upload.uploader'`.

- [ ] **Step 3: Write minimal implementation**

`src/upload/uploader.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_uploader.py -v`
Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add src/upload/uploader.py tests/test_uploader.py
git commit -m "Add single-folder YouTube upload with retry and quota tracking (#20)"
```

---

### Task 4: Batch orchestration

**Files:**
- Modify: `src/upload/uploader.py` (add `BatchUploadResult` + `upload_batch`)
- Modify: `tests/test_uploader.py` (add batch tests)
- Modify: `src/upload/__init__.py` (export new names)

**Interfaces:**
- Consumes: `YouTubeUploader.upload_folder`, `UploadResult` from Task 3.
- Produces: `BatchUploadResult(results: List[UploadResult])` with properties `succeeded`, `failed`, `skipped` and `to_dict`/`to_json`; `YouTubeUploader.upload_batch() -> BatchUploadResult`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_uploader.py`)

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_uploader.py -v`
Expected: the new batch tests FAIL with `AttributeError: 'YouTubeUploader' object has no attribute 'upload_batch'` (or `ImportError` for `BatchUploadResult`).

- [ ] **Step 3: Write minimal implementation**

Append to `src/upload/uploader.py`:
```python
@dataclass
class BatchUploadResult:
    results: List[UploadResult]

    @property
    def succeeded(self) -> List[UploadResult]:
        return [r for r in self.results if r.status == UPLOADED]

    @property
    def failed(self) -> List[UploadResult]:
        return [r for r in self.results if r.status == FAILED]

    @property
    def skipped(self) -> List[UploadResult]:
        return [r for r in self.results if r.status == SKIPPED]

    def to_dict(self) -> Dict:
        return {
            "succeeded": [r.to_dict() for r in self.succeeded],
            "failed": [r.to_dict() for r in self.failed],
            "skipped": [r.to_dict() for r in self.skipped],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
```

Add to `YouTubeUploader`:
```python
    def upload_batch(self) -> BatchUploadResult:
        if not self.approved_dir.is_dir():
            return BatchUploadResult(results=[])
        results = []
        for folder in sorted(
            (p for p in self.approved_dir.iterdir() if p.is_dir())
        ):
            results.append(self.upload_folder(folder))
            if results[-1].status == SKIPPED:
                break
        return BatchUploadResult(results=results)
```

Update `src/upload/__init__.py`:
```python
from .quota import QuotaExceededError, QuotaTracker
from .uploader import BatchUploadResult, UploadError, UploadResult, YouTubeUploader

__all__ = [
    "BatchUploadResult",
    "QuotaExceededError",
    "QuotaTracker",
    "UploadError",
    "UploadResult",
    "YouTubeUploader",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_uploader.py -v`
Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git add src/upload/__init__.py src/upload/uploader.py tests/test_uploader.py
git commit -m "Add batch upload orchestration for the approved queue (#20)"
```

---

### Task 5: Full suite, review, push, close

- [ ] Run: `venv\Scripts\python -m pytest -q` → all tests pass (existing 212 passed / 1 skipped + 36 new).
- [ ] Two-axis code review (standards + spec) of the diff vs `fe1c190` (handoff fixed point); spawn 2 parallel general sub-agents.
- [ ] Commit any review fixes; push to `master`.
- [ ] Close #20 with a summary comment (no secrets in messages).
