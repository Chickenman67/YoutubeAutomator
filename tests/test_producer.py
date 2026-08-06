import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from fact_check.fact_checker import Confidence, FactCheckReport, FactCheckResult
from metadata.generator import Metadata
from pipeline.exporter import ExportResult
from pipeline.producer import ProductionResult, VideoProducer
from pipeline.staging import StagingManifest
from pipeline.state_machine import PipelineResult, Stage
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


def completed_result(topic="Test Topic", scene_count=6):
    return PipelineResult(
        topic=topic,
        stage=Stage.METADATA_GENERATED,
        status="completed",
        script=make_script(topic, scene_count),
        fact_check=make_report(topic),
        metadata=make_metadata(topic),
    )


class FakeRenderer:
    def __init__(self):
        self.calls = []

    def render(self, scene, output_name, output_dir, duration=None, width=None, height=None, fps=None):
        self.calls.append((scene.scene_id, output_name, width, height, fps))
        media = Path(output_dir) / "media"
        media.mkdir(parents=True, exist_ok=True)
        path = media / f"{output_name}.mp4"
        path.write_bytes(b"fake")
        from video_production import RenderResult
        return RenderResult(path=path, width=width or 1080, height=height or 1920,
                            duration=30.0, source_path=Path(output_dir) / f"{output_name}.py")


class FakeVoiceover:
    def __init__(self):
        self.calls = []

    def generate(self, scene, output_path, voice=None):
        self.calls.append((scene.scene_id, voice))
        path = Path(output_path)
        path.write_bytes(b"fake")
        from video_production import VoiceoverResult
        return VoiceoverResult(path=path, duration=30.0, voice=voice)


class FakeAssembler:
    def __init__(self):
        self.calls = []

    def assemble(self, video_path, audio_path, output_path, width=None, height=None, fps=None):
        self.calls.append((Path(video_path).name, Path(audio_path).name, Path(output_path).name,
                           width, height, fps))
        path = Path(output_path)
        path.write_bytes(b"fake")
        from video_production import AssemblyResult
        return AssemblyResult(path=path, width=width or 1080, height=height or 1920,
                              duration=30.0, has_audio=True)


class FakeStitcher:
    def __init__(self):
        self.calls = []

    def stitch(self, scene_paths, output_path, width=None, height=None, fps=None):
        self.calls.append((list(scene_paths), Path(output_path).name, width, height, fps))
        path = Path(output_path)
        path.write_bytes(b"fake")
        from video_production import StitchResult
        return StitchResult(path=path, width=width or 1920, height=height or 1080,
                            duration=180.0, scene_count=len(scene_paths))


class FakeThumbnailer:
    def __init__(self):
        self.calls = []

    def generate(self, video_path, title, output_path, frame_time=3.0, width=None, height=None, font_path=None):
        self.calls.append((video_path, title, Path(output_path).name))
        path = Path(output_path)
        path.write_bytes(b"fake")
        from video_production import ThumbnailResult
        return ThumbnailResult(path=path, width=1280, height=720, source_path=Path(video_path),
                               frame_time=frame_time, title=title)


class FakeStagingCollector:
    def __init__(self, staging_dir="queue/staging"):
        self.staging_dir = Path(staging_dir)
        self.calls = []

    def collect(self, video_id, script, fact_check, metadata, midform_path, short_paths, thumbnail_path, staging_dir=None):
        self.calls.append((video_id, midform_path, list(short_paths), thumbnail_path))
        directory = Path(staging_dir or self.staging_dir) / video_id
        directory.mkdir(parents=True, exist_ok=True)
        return StagingManifest(
            video_id=video_id,
            directory=directory,
            midform=directory / "midform.mp4",
            shorts=[directory / "short_01.mp4"],
            thumbnail=directory / "thumbnail.png",
            metadata_file=directory / "metadata.json",
            fact_check_file=directory / "fact_check.json",
            script_file=directory / "script.json",
        )


class FakeExporter:
    def __init__(self, pending_dir="queue/pending_review"):
        self.pending_dir = Path(pending_dir)
        self.calls = []

    def export(self, manifest, pending_dir=None, video_id=None):
        self.calls.append(manifest)
        dest = Path(pending_dir or self.pending_dir) / manifest.video_id
        dest.mkdir(parents=True, exist_ok=True)
        assets = [dest / Path(a).name for a in manifest.assets]
        for p in assets:
            p.write_bytes(b"fake")
        master = dest / "metadata.json"
        master.write_text("{}", encoding="utf-8")
        return ExportResult(video_id=manifest.video_id, directory=dest, assets=assets, metadata=master)


def make_fakes(tmp_path):
    return {
        "renderer": FakeRenderer(),
        "voiceover": FakeVoiceover(),
        "assembler": FakeAssembler(),
        "stitcher": FakeStitcher(),
        "thumbnailer": FakeThumbnailer(),
        "staging_collector": FakeStagingCollector(staging_dir=str(tmp_path / "staging")),
        "exporter": FakeExporter(pending_dir=str(tmp_path / "pending_review")),
    }


def test_production_result_roundtrip():
    result = ProductionResult(
        topic="T", status="completed", stage="exported", video_id="v1",
        directory=Path("q/pending_review/v1"), assets=[Path("a.mp4")],
        metadata_file=Path("q/pending_review/v1/metadata.json"),
    )
    assert result.completed
    data = result.to_dict()
    assert data["topic"] == "T"
    assert data["status"] == "completed"
    assert data["stage"] == "exported"
    assert data["video_id"] == "v1"
    assert data["directory"] == str(Path("q/pending_review/v1"))
    assert data["assets"] == ["a.mp4"]
    assert data["metadata_file"] == str(Path("q/pending_review/v1/metadata.json"))
    assert json.loads(result.to_json())["status"] == "completed"


def test_production_result_failed_not_completed():
    result = ProductionResult(topic="T", status="failed", stage="render", error="render failed: boom")
    assert not result.completed
    parsed = json.loads(result.to_json())
    assert parsed["error"] == "render failed: boom"
    assert "script" not in parsed


def test_produce_non_completed_returns_failed_without_writes(tmp_path):
    fakes = make_fakes(tmp_path)
    producer = VideoProducer(**fakes, work_dir=str(tmp_path / "work"))
    result = PipelineResult(
        topic="T", stage=Stage.METADATA_GENERATED, status="failed",
        error="metadata generation failed: boom",
    )
    out = producer.produce(result)
    assert out.status == "failed"
    assert out.stage == "pipeline"
    assert out.error == "metadata generation failed: boom"
    assert not (tmp_path / "work").exists()
    assert not fakes["renderer"].calls
    assert not fakes["exporter"].calls
