# Review Dashboard Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each task below. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flask backend (`src/dashboard/`) that serves pending Videos from `queue/pending_review/` as JSON, serves their media/thumbnail assets, and moves approved/rejected Videos into `queue/approved/` and `queue/rejected/`.

**Architecture:** A `DashboardStore` class encapsulates all `queue/` filesystem operations (list, get, approve, reject) with an injected `queue_root` seam. A `create_app(store=None, queue_root="queue")` Flask app factory exposes the endpoints `GET /pending`, `GET /video/<id>`, `POST /approve/<id>`, `POST /reject/<id>` plus a `GET /video/<id>/asset/<filename>` file-serving route. The store parses the master `metadata.json` produced by the #17 exporter.

**Tech Stack:** Python 3.14, Flask 3.1.3, Flask-CORS 6.0.5, stdlib (`dataclasses`, `json`, `logging`, `shutil`, `pathlib`). pytest + Flask test client with temp dirs and the existing exporter for integration-style fixtures — no network.

**Design context:** Consumes the folder layout from #17 (`src/pipeline/exporter.py`): `queue/pending_review/{video_id}/` holds `{video_id}_midform.mp4`, `{video_id}_short_NN.mp4`, `{video_id}_thumbnail.png`, `{video_id}_metadata.json`, `{video_id}_fact_check.json`, `{video_id}_script.json`, plus a nested master `metadata.json` with shape `{video_id, topic, metadata{title,description,tags,category}, fact_check{topic,results,low_confidence}, assets{midform,shorts,thumbnail}}`. Glossary (`CONTEXT.md`): Queue states `pending_review/ → approved/ → uploaded/` and `rejected/` (manual review).

## Global Constraints

- Test runner: `venv\Scripts\python -m pytest -q` (full suite). For one file: `venv\Scripts\python -m pytest tests\test_dashboard.py -v`.
- Follow repo conventions: dataclass result objects with `to_dict`/`to_json`, typed injected seams, `Path.mkdir(parents=True, exist_ok=True)`, `logging.getLogger(__name__)`, no comments in production code unless asked.
- Repo test convention: `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))` at top of every test file.
- Keep the exporter's on-disk layout unchanged; the store reads it, never writes staging files.
- Reject moves to `rejected/` (per issue AC and spec); approve moves to `approved/`.
- Return JSON for every endpoint; missing Videos → `404` with a `{"error": ...}` body.

---

### Task 1: DashboardStore (filesystem seam)

**Files:**
- Create: `src/dashboard/store.py`
- Create: `tests/test_store.py`

**Interfaces:**
- Consumes: `queue/pending_review/{video_id}/metadata.json` (master, from #17), plus `{video_id}_script.json`.
- Produces: `VideoSummary` (`video_id`, `topic`, `title`, `thumbnail`), `VideoPackage` (`video_id`, `directory`, `topic`, `metadata`, `fact_check`, `script`, `assets`), and `DashboardStore` with `list_pending() -> List[VideoSummary]`, `get_video(video_id) -> VideoPackage`, `approve(video_id) -> Path`, `reject(video_id) -> Path`. All have `to_dict`/`to_json`. Methods raise `FileNotFoundError` on an unknown/missing Video.

- [ ] **Step 1: Write the failing tests**

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from fact_check.fact_checker import Confidence, FactCheckReport, FactCheckResult
from metadata.generator import Metadata
from pipeline.exporter import QueueExporter
from pipeline.staging import StagingCollector
from script_generation.schema import Scene, Script
from dashboard.store import DashboardStore, VideoPackage, VideoSummary


def make_script(topic="Test Topic", scene_count=6):
    scenes = [
        Scene(
            scene_id=i,
            narration="word " * 250,
            key_visual_keywords=["stick figure walking", "globe rotating", "clock ticking"],
            facts=["Fact one", "Fact two", "Fact three"],
        )
        for i in range(1, scene_count + 1)
    ]
    return Script(topic=topic, scenes=scenes)


def make_report(topic="Test Topic"):
    return FactCheckReport(
        topic=topic,
        results=[FactCheckResult(claim="Fact one", confidence=Confidence.HIGH)],
    )


def make_metadata(topic="Test Topic"):
    return Metadata(title=f"{topic} Explained", description="desc", tags=["tag"])


def make_media(tmp_path, count=6):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    mid = src / "midform.mp4"
    mid.write_bytes(b"mid")
    shorts = []
    for i in range(count):
        p = src / f"short_{i}.mp4"
        p.write_bytes(b"short")
        shorts.append(str(p))
    thumb = src / "thumb.png"
    thumb.write_bytes(b"png")
    return str(mid), shorts, str(thumb)


def seed_pending(tmp_path, queue_root, video_id="vid-1", topic="Space"):
    mid, shorts, thumb = make_media(tmp_path)
    manifest = StagingCollector().collect(
        video_id, make_script(topic), make_report(topic), make_metadata(topic),
        mid, shorts, thumb, staging_dir=str(queue_root / "staging"),
    )
    QueueExporter(pending_dir=str(queue_root / "pending_review")).export(manifest)
    return queue_root / "pending_review" / video_id


def test_list_pending_returns_video_summaries(tmp_path):
    queue_root = tmp_path / "queue"
    seed_pending(tmp_path, queue_root, video_id="vid-1", topic="Space")
    seed_pending(tmp_path, queue_root, video_id="vid-2", topic="Mars")
    store = DashboardStore(queue_root=str(queue_root))
    videos = store.list_pending()
    assert len(videos) == 2
    assert all(isinstance(v, VideoSummary) for v in videos)
    by_id = {v.video_id: v for v in videos}
    assert by_id["vid-1"].topic == "Space"
    assert by_id["vid-1"].title == "Space Explained"
    assert by_id["vid-1"].thumbnail == "vid-1_thumbnail.png"


def test_list_pending_skips_dirs_without_metadata(tmp_path):
    queue_root = tmp_path / "queue"
    seed_pending(tmp_path, queue_root)
    stray = queue_root / "pending_review" / "not-a-video"
    stray.mkdir(parents=True, exist_ok=True)
    (stray / "junk.txt").write_text("x")
    store = DashboardStore(queue_root=str(queue_root))
    assert [v.video_id for v in store.list_pending()] == ["vid-1"]


def test_list_pending_returns_empty_when_dir_missing(tmp_path):
    store = DashboardStore(queue_root=str(tmp_path / "queue"))
    assert store.list_pending() == []


def test_get_video_returns_package(tmp_path):
    queue_root = tmp_path / "queue"
    seed_pending(tmp_path, queue_root)
    store = DashboardStore(queue_root=str(queue_root))
    pkg = store.get_video("vid-1")
    assert isinstance(pkg, VideoPackage)
    assert pkg.video_id == "vid-1"
    assert pkg.topic == "Space"
    assert pkg.metadata["title"] == "Space Explained"
    assert pkg.assets["midform"] == "vid-1_midform.mp4"
    assert len(pkg.assets["shorts"]) == 6
    assert pkg.assets["thumbnail"] == "vid-1_thumbnail.png"
    assert pkg.script["topic"] == "Space"


def test_get_video_raises_for_missing(tmp_path):
    store = DashboardStore(queue_root=str(tmp_path / "queue"))
    with pytest.raises(FileNotFoundError):
        store.get_video("nope")


def test_approve_moves_folder_to_approved(tmp_path):
    queue_root = tmp_path / "queue"
    seed_pending(tmp_path, queue_root)
    store = DashboardStore(queue_root=str(queue_root))
    dest = store.approve("vid-1")
    assert dest == queue_root / "approved" / "vid-1"
    assert dest.is_dir()
    assert not (queue_root / "pending_review" / "vid-1").exists()
    assert (dest / "metadata.json").exists()


def test_reject_moves_folder_to_rejected(tmp_path):
    queue_root = tmp_path / "queue"
    seed_pending(tmp_path, queue_root)
    store = DashboardStore(queue_root=str(queue_root))
    dest = store.reject("vid-1")
    assert dest == queue_root / "rejected" / "vid-1"
    assert dest.is_dir()
    assert not (queue_root / "pending_review" / "vid-1").exists()


def test_approve_missing_raises(tmp_path):
    store = DashboardStore(queue_root=str(tmp_path / "queue"))
    with pytest.raises(FileNotFoundError):
        store.approve("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dashboard.store'`.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

Note: `secure_filename` is applied defensively to keep filenames safe when moving; the exporter already produces safe prefixed names.

- [ ] **Step 4: Run test to verify it passes**

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/store.py tests/test_store.py
git commit -m "Add dashboard store managing pending review queue folders (#18)"
```

### Task 2: Flask app factory + endpoints

**Files:**
- Create: `src/dashboard/__init__.py`
- Create: `src/dashboard/app.py`
- Create: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `DashboardStore`, `VideoSummary`, `VideoPackage` from Task 1.
- Produces: `create_app(store: Optional[DashboardStore] = None, queue_root: str = "queue") -> Flask`. Endpoints:
  - `GET /pending` → `{"videos": [VideoSummary.to_dict(), ...]}`
  - `GET /video/<video_id>` → `VideoPackage.to_dict()` (or `404 {"error": ...}`)
  - `POST /approve/<video_id>` → `{"video_id": ..., "status": "approved"}` (or `404`)
  - `POST /reject/<video_id>` → `{"video_id": ..., "status": "rejected"}` (or `404`)
  - `GET /video/<video_id>/asset/<path:filename>` → media file via `send_from_directory` (or `404`)

- [ ] **Step 1: Write the failing tests**

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from fact_check.fact_checker import Confidence, FactCheckReport, FactCheckResult
from metadata.generator import Metadata
from pipeline.exporter import QueueExporter
from pipeline.staging import StagingCollector
from script_generation.schema import Scene, Script
from dashboard.app import create_app
from dashboard.store import DashboardStore


def make_script(topic="Test Topic", scene_count=6):
    scenes = [
        Scene(
            scene_id=i,
            narration="word " * 250,
            key_visual_keywords=["stick figure walking", "globe rotating", "clock ticking"],
            facts=["Fact one", "Fact two", "Fact three"],
        )
        for i in range(1, scene_count + 1)
    ]
    return Script(topic=topic, scenes=scenes)


def make_report(topic="Test Topic"):
    return FactCheckReport(
        topic=topic,
        results=[FactCheckResult(claim="Fact one", confidence=Confidence.HIGH)],
    )


def make_metadata(topic="Test Topic"):
    return Metadata(title=f"{topic} Explained", description="desc", tags=["tag"])


def make_media(tmp_path, count=6):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    mid = src / "midform.mp4"
    mid.write_bytes(b"mid")
    shorts = []
    for i in range(count):
        p = src / f"short_{i}.mp4"
        p.write_bytes(b"short")
        shorts.append(str(p))
    thumb = src / "thumb.png"
    thumb.write_bytes(b"png")
    return str(mid), shorts, str(thumb)


def seed_pending(tmp_path, queue_root, video_id="vid-1", topic="Space"):
    mid, shorts, thumb = make_media(tmp_path)
    manifest = StagingCollector().collect(
        video_id, make_script(topic), make_report(topic), make_metadata(topic),
        mid, shorts, thumb, staging_dir=str(queue_root / "staging"),
    )
    QueueExporter(pending_dir=str(queue_root / "pending_review")).export(manifest)


@pytest.fixture
def client(tmp_path):
    queue_root = tmp_path / "queue"
    seed_pending(tmp_path, queue_root)
    app = create_app(store=DashboardStore(queue_root=str(queue_root)))
    app.config["TESTING"] = True
    return app.test_client(), queue_root, tmp_path


def test_get_pending_returns_json_list(client):
    cli, _, _ = client
    resp = cli.get("/pending")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["videos"][0]["video_id"] == "vid-1"
    assert data["videos"][0]["topic"] == "Space"


def test_get_video_returns_details(client):
    cli, _, _ = client
    resp = cli.get("/video/vid-1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["metadata"]["title"] == "Space Explained"
    assert len(data["assets"]["shorts"]) == 6
    assert data["script"]["topic"] == "Space"


def test_get_video_missing_returns_404(client):
    cli, _, _ = client
    resp = cli.get("/video/nope")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_post_approve_moves_and_returns_json(client):
    cli, queue_root, _ = client
    resp = cli.post("/approve/vid-1")
    assert resp.status_code == 200
    assert resp.get_json() == {"video_id": "vid-1", "status": "approved"}
    assert (queue_root / "approved" / "vid-1").is_dir()
    assert not (queue_root / "pending_review" / "vid-1").exists()


def test_post_reject_moves_and_returns_json(client):
    cli, queue_root, _ = client
    resp = cli.post("/reject/vid-1")
    assert resp.status_code == 200
    assert resp.get_json() == {"video_id": "vid-1", "status": "rejected"}
    assert (queue_root / "rejected" / "vid-1").is_dir()


def test_post_approve_missing_returns_404(client):
    cli, _, _ = client
    resp = cli.post("/approve/nope")
    assert resp.status_code == 404


def test_serve_asset_returns_media_file(client):
    cli, _, _ = client
    resp = cli.get("/video/vid-1/asset/vid-1_midform.mp4")
    assert resp.status_code == 200
    assert resp.data == b"mid"
    assert "video/mp4" in resp.content_type


def test_serve_asset_unknown_video_returns_404(client):
    cli, _, _ = client
    resp = cli.get("/video/nope/asset/x.mp4")
    assert resp.status_code == 404


def test_create_app_defaults_to_queue_root(tmp_path, monkeypatch):
    queue_root = tmp_path / "queue"
    seed_pending(tmp_path, queue_root)
    monkeypatch.chdir(tmp_path)
    app = create_app(store=DashboardStore(queue_root=str(queue_root)))
    app.config["TESTING"] = True
    resp = app.test_client().get("/pending")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_dashboard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dashboard.app'`.

- [ ] **Step 3: Write minimal implementation**

`src/dashboard/__init__.py`:
```python
from .app import create_app
from .store import DashboardStore, VideoPackage, VideoSummary

__all__ = ["create_app", "DashboardStore", "VideoPackage", "VideoSummary"]
```

`src/dashboard/app.py`:
```python
import logging
from typing import Optional

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from dashboard.store import DashboardStore


def create_app(
    store: Optional[DashboardStore] = None,
    queue_root: str = "queue",
) -> Flask:
    app = Flask(__name__)
    CORS(app)
    app.config["JSON_SORT_KEYS"] = False
    store = store or DashboardStore(queue_root=queue_root)
    logger = logging.getLogger(__name__)

    @app.get("/pending")
    def list_pending():
        return jsonify({"videos": [v.to_dict() for v in store.list_pending()]})

    @app.get("/video/<video_id>")
    def video_details(video_id):
        try:
            package = store.get_video(video_id)
        except FileNotFoundError:
            return jsonify({"error": f"video not found: {video_id}"}), 404
        return jsonify(package.to_dict())

    @app.post("/approve/<video_id>")
    def approve(video_id):
        try:
            store.approve(video_id)
        except FileNotFoundError:
            return jsonify({"error": f"video not found: {video_id}"}), 404
        return jsonify({"video_id": video_id, "status": "approved"})

    @app.post("/reject/<video_id>")
    def reject(video_id):
        try:
            store.reject(video_id)
        except FileNotFoundError:
            return jsonify({"error": f"video not found: {video_id}"}), 404
        return jsonify({"video_id": video_id, "status": "rejected"})

    @app.get("/video/<video_id>/asset/<path:filename>")
    def serve_asset(video_id, filename):
        folder = store.pending_dir / video_id
        if not folder.is_dir():
            return jsonify({"error": f"video not found: {video_id}"}), 404
        return send_from_directory(folder, filename)

    return app


if __name__ == "__main__":
    create_app().run(debug=True, host="127.0.0.1", port=5000)
```

- [ ] **Step 4: Run test to verify it passes**

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/__init__.py src/dashboard/app.py tests/test_dashboard.py
git commit -m "Add Flask backend serving pending review queue and approve/reject (#18)"
```

### Task 3: Full suite, review, commit

- [ ] Run: `venv\Scripts\python -m pytest -q` → all tests pass (existing 189 + 19 new).
- [ ] Two-axis code review (standards + spec) of the diff vs HEAD.
- [ ] Commit any review fixes; push to `master`; close #18 with a summary comment (no secrets in messages).
