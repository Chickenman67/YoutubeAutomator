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
