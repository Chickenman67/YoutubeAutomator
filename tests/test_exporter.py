import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from fact_check.fact_checker import Confidence, FactCheckReport, FactCheckResult
from metadata.generator import Metadata
from pipeline.exporter import ExportResult, QueueExporter, generate_video_id
from pipeline.staging import StagingCollector
from script_generation.schema import Scene, Script


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


def make_manifest(tmp_path):
    mid, shorts, thumb = make_media(tmp_path)
    return StagingCollector().collect(
        "vid-1", make_script("Space"), make_report("Space"), make_metadata("Space"),
        mid, shorts, thumb, staging_dir=str(tmp_path / "staging"),
    )


def test_generate_video_id_has_timestamp_and_random_suffix():
    video_id = generate_video_id()
    stamp, suffix = video_id.rsplit("-", 1)
    assert len(stamp) == 15
    assert len(suffix) == 6
    assert all(c in "0123456789abcdef" for c in suffix)


def test_generate_video_ids_are_unique():
    assert generate_video_id() != generate_video_id()


def test_generate_video_id_uses_provided_now():
    from datetime import datetime

    vid = generate_video_id(datetime(2026, 8, 4, 10, 30, 0))
    assert vid.startswith("20260804-103000-")


def test_export_copies_assets_into_pending_review(tmp_path):
    manifest = make_manifest(tmp_path)
    result = QueueExporter().export(manifest, pending_dir=str(tmp_path / "pending"))
    assert isinstance(result, ExportResult)
    assert result.video_id == "vid-1"
    assert result.directory == tmp_path / "pending" / "vid-1"
    assert result.directory.is_dir()
    for asset in result.assets:
        assert asset.exists()
    staged_names = {p.name for p in manifest.assets}
    exported_names = {p.name for p in result.assets}
    assert staged_names == exported_names


def test_export_writes_master_metadata_json(tmp_path):
    manifest = make_manifest(tmp_path)
    result = QueueExporter().export(manifest, pending_dir=str(tmp_path / "pending"))
    master = json.loads(result.metadata.read_text(encoding="utf-8"))
    assert master["video_id"] == "vid-1"
    assert master["topic"] == "Space"
    assert master["metadata"]["title"] == "Space Explained"
    assert master["fact_check"]["results"]
    assert master["assets"]["midform"] == "vid-1_midform.mp4"
    assert len(master["assets"]["shorts"]) == 6
    assert master["assets"]["thumbnail"] == "vid-1_thumbnail.png"


def test_export_respects_video_id_override(tmp_path):
    manifest = make_manifest(tmp_path)
    result = QueueExporter().export(
        manifest, pending_dir=str(tmp_path / "pending"), video_id="vid-9"
    )
    assert result.video_id == "vid-9"
    assert result.directory == tmp_path / "pending" / "vid-9"


def test_export_uses_custom_pending_dir(tmp_path):
    manifest = make_manifest(tmp_path)
    result = QueueExporter(pending_dir=str(tmp_path / "custom")).export(manifest)
    assert result.directory.parent == tmp_path / "custom"


def test_export_logs_completion(caplog, tmp_path):
    import logging

    manifest = make_manifest(tmp_path)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        QueueExporter().export(manifest, pending_dir=str(tmp_path / "pending"))
    assert "vid-1" in caplog.text
    assert "exported" in caplog.text


def test_export_result_serializes_to_dict_and_json(tmp_path):
    manifest = make_manifest(tmp_path)
    result = QueueExporter().export(manifest, pending_dir=str(tmp_path / "pending"))
    data = result.to_dict()
    assert data["video_id"] == "vid-1"
    assert Path(data["directory"]).is_dir()
    assert json.loads(result.to_json())["video_id"] == "vid-1"
