import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from fact_check.fact_checker import Confidence, FactCheckReport, FactCheckResult
from metadata.generator import Metadata
from pipeline.staging import StagingCollector, StagingManifest
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


def test_collect_organizes_assets_into_video_id_folder(tmp_path):
    mid, shorts, thumb = make_media(tmp_path)
    collector = StagingCollector()
    manifest = collector.collect(
        "vid-1", make_script(), make_report(), make_metadata(), mid, shorts, thumb,
        staging_dir=str(tmp_path / "staging"),
    )
    assert isinstance(manifest, StagingManifest)
    assert manifest.video_id == "vid-1"
    assert manifest.directory == tmp_path / "staging" / "vid-1"
    assert manifest.directory.is_dir()
    for asset in manifest.assets:
        assert asset.exists()


def test_collect_uses_video_id_prefix_naming(tmp_path):
    mid, shorts, thumb = make_media(tmp_path)
    manifest = StagingCollector().collect(
        "vid-1", make_script(), make_report(), make_metadata(), mid, shorts, thumb,
        staging_dir=str(tmp_path / "staging"),
    )
    names = sorted(p.name for p in manifest.directory.iterdir())
    assert names == [
        "vid-1_fact_check.json",
        "vid-1_metadata.json",
        "vid-1_midform.mp4",
        "vid-1_script.json",
        "vid-1_short_01.mp4",
        "vid-1_short_02.mp4",
        "vid-1_short_03.mp4",
        "vid-1_short_04.mp4",
        "vid-1_short_05.mp4",
        "vid-1_short_06.mp4",
        "vid-1_thumbnail.png",
    ]


def test_collect_manifest_lists_every_asset(tmp_path):
    mid, shorts, thumb = make_media(tmp_path)
    manifest = StagingCollector().collect(
        "vid-1", make_script(), make_report(), make_metadata(), mid, shorts, thumb,
        staging_dir=str(tmp_path / "staging"),
    )
    assert manifest.midform.name == "vid-1_midform.mp4"
    assert len(manifest.shorts) == 6
    assert manifest.shorts[0].name == "vid-1_short_01.mp4"
    assert manifest.thumbnail.name == "vid-1_thumbnail.png"
    assert manifest.metadata_file.name == "vid-1_metadata.json"
    assert manifest.fact_check_file.name == "vid-1_fact_check.json"
    assert manifest.script_file.name == "vid-1_script.json"
    assert len(manifest.assets) == 11


def test_manifest_to_json_lists_asset_paths(tmp_path):
    mid, shorts, thumb = make_media(tmp_path)
    manifest = StagingCollector().collect(
        "vid-1", make_script(), make_report(), make_metadata(), mid, shorts, thumb,
        staging_dir=str(tmp_path / "staging"),
    )
    payload = json.loads(manifest.to_json())
    assert payload["video_id"] == "vid-1"
    assert len(payload["shorts"]) == 6
    assert payload["midform"].endswith("vid-1_midform.mp4")
    assert Path(payload["directory"]).name == "vid-1"


def test_collect_validates_missing_midform(tmp_path):
    mid, shorts, thumb = make_media(tmp_path)
    with pytest.raises(FileNotFoundError):
        StagingCollector().collect(
            "vid-1", make_script(), make_report(), make_metadata(),
            str(tmp_path / "src" / "nope.mp4"), shorts, thumb,
            staging_dir=str(tmp_path / "staging"),
        )
    assert not (tmp_path / "staging").exists()


def test_collect_validates_missing_short(tmp_path):
    mid, shorts, thumb = make_media(tmp_path)
    missing = shorts[:-1] + [str(tmp_path / "src" / "nope.mp4")]
    with pytest.raises(FileNotFoundError):
        StagingCollector().collect(
            "vid-1", make_script(), make_report(), make_metadata(),
            mid, missing, thumb,
            staging_dir=str(tmp_path / "staging"),
        )
    assert not (tmp_path / "staging").exists()


def test_collect_validates_short_count_matches_scenes(tmp_path):
    mid, shorts, thumb = make_media(tmp_path, count=6)
    script = make_script(scene_count=6)
    with pytest.raises(ValueError, match="short"):
        StagingCollector().collect(
            "vid-1", script, make_report(), make_metadata(),
            mid, shorts[:3], thumb,
            staging_dir=str(tmp_path / "staging"),
        )
    assert not (tmp_path / "staging").exists()


def test_collect_validates_required_data(tmp_path):
    mid, shorts, thumb = make_media(tmp_path)
    with pytest.raises(ValueError):
        StagingCollector().collect(
            "vid-1", None, make_report(), make_metadata(),
            mid, shorts, thumb, staging_dir=str(tmp_path / "staging"),
        )
    with pytest.raises(ValueError):
        StagingCollector().collect(
            "vid-1", make_script(), None, make_metadata(),
            mid, shorts, thumb, staging_dir=str(tmp_path / "staging"),
        )
    with pytest.raises(ValueError):
        StagingCollector().collect(
            "vid-1", make_script(), make_report(), None,
            mid, shorts, thumb, staging_dir=str(tmp_path / "staging"),
        )
    assert not (tmp_path / "staging").exists()


def test_collect_validates_video_id(tmp_path):
    mid, shorts, thumb = make_media(tmp_path)
    with pytest.raises(ValueError, match="video_id"):
        StagingCollector().collect(
            "", make_script(), make_report(), make_metadata(),
            mid, shorts, thumb, staging_dir=str(tmp_path / "staging"),
        )
    assert not (tmp_path / "staging").exists()


def test_collect_writes_metadata_fact_check_and_script_json(tmp_path):
    mid, shorts, thumb = make_media(tmp_path)
    manifest = StagingCollector().collect(
        "vid-1", make_script("Space"), make_report("Space"), make_metadata("Space"),
        mid, shorts, thumb, staging_dir=str(tmp_path / "staging"),
    )
    meta = json.loads(manifest.metadata_file.read_text(encoding="utf-8"))
    facts = json.loads(manifest.fact_check_file.read_text(encoding="utf-8"))
    script = json.loads(manifest.script_file.read_text(encoding="utf-8"))
    assert meta["title"] == "Space Explained"
    assert facts["topic"] == "Space"
    assert facts["results"]
    assert script["topic"] == "Space"
    assert len(script["scenes"]) == 6
