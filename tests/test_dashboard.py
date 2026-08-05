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


def test_serve_asset_missing_file_returns_404(client):
    cli, _, _ = client
    resp = cli.get("/video/vid-1/asset/does_not_exist.mp4")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_create_app_defaults_to_queue_root(tmp_path, monkeypatch):
    queue_root = tmp_path / "queue"
    seed_pending(tmp_path, queue_root)
    monkeypatch.chdir(tmp_path)
    app = create_app(store=DashboardStore(queue_root=str(queue_root)))
    app.config["TESTING"] = True
    resp = app.test_client().get("/pending")
    assert resp.status_code == 200


def test_index_serves_frontend_html(client):
    cli, _, _ = client
    resp = cli.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    assert "Review Dashboard" in resp.get_data(as_text=True)


def test_index_links_to_module_bundle(client):
    cli, _, _ = client
    html = cli.get("/").get_data(as_text=True)
    assert '<script type="module" src="/static/app.mjs">' in html
    assert '/static/style.css' in html


def test_static_serves_frontend_assets(client):
    cli, _, _ = client
    for path in ["/static/core.mjs", "/static/app.mjs", "/static/style.css"]:
        resp = cli.get(path)
        assert resp.status_code == 200, path
    assert "text/javascript" in cli.get("/static/core.mjs").content_type
