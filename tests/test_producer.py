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

class FailOnCall:
    def __init__(self, wrapped):
        self._wrapped = wrapped

    def __getattr__(self, name):
        attr = getattr(self._wrapped, name)
        if not callable(attr):
            return attr

        def raiser(*args, **kwargs):
            raise RuntimeError("boom")

        return raiser


EXPECTED_STAGE = {
    "renderer": "render",
    "voiceover": "voiceover",
    "assembler": "assemble",
    "stitcher": "stitch",
    "thumbnailer": "thumbnail",
    "staging_collector": "stage",
    "exporter": "export",
}


def test_produce_happy_path_visits_every_scene_twice(tmp_path):
    fakes = make_fakes(tmp_path)
    producer = VideoProducer(**fakes, work_dir=str(tmp_path / "work"))

    out = producer.produce(completed_result(scene_count=6))

    assert out.status == "completed"
    assert out.stage == "exported"
    assert out.video_id
    assert out.directory == (tmp_path / "pending_review" / out.video_id)
    assert out.metadata_file == (tmp_path / "pending_review" / out.video_id / "metadata.json")
    assert out.assets

    render_calls = fakes["renderer"].calls
    assert len(render_calls) == 12
    landscape = [c for c in render_calls if "_L" in c[1]]
    vertical = [c for c in render_calls if "_V" in c[1]]
    assert [c[0] for c in landscape] == [1, 2, 3, 4, 5, 6]
    assert [c[0] for c in vertical] == [1, 2, 3, 4, 5, 6]
    assert all(c[2] == 1920 and c[3] == 1080 for c in landscape)
    assert all(c[2] == 1080 and c[3] == 1920 for c in vertical)

    assert len(fakes["voiceover"].calls) == 6
    assert all(c[1] == "en-US-JennyNeural" for c in fakes["voiceover"].calls)

    assert len(fakes["assembler"].calls) == 12
    for i in range(1, 7):
        landscape_assemble = fakes["assembler"].calls[2 * (i - 1)]
        vertical_assemble = fakes["assembler"].calls[2 * (i - 1) + 1]
        assert landscape_assemble[0] == f"scene_{i}_L.mp4"
        assert landscape_assemble[1] == f"voice_{i}.mp3"
        assert landscape_assemble[2] == f"scene_{i}_L.mp4"
        assert landscape_assemble[3] == 1920 and landscape_assemble[4] == 1080
        assert vertical_assemble[0] == f"scene_{i}_V.mp4"
        assert vertical_assemble[1] == f"voice_{i}.mp3"
        assert vertical_assemble[2] == f"short_{i:02d}.mp4"
        assert vertical_assemble[3] == 1080 and vertical_assemble[4] == 1920

    assert len(fakes["stitcher"].calls) == 1
    scene_paths, output_name, width, height, fps = fakes["stitcher"].calls[0]
    assert output_name == "midform.mp4"
    assert [Path(p).name for p in scene_paths] == [f"scene_{i}_L.mp4" for i in range(1, 7)]
    assert width == 1920 and height == 1080

    assert len(fakes["thumbnailer"].calls) == 1
    video_path, title, thumb_name = fakes["thumbnailer"].calls[0]
    assert thumb_name == "thumbnail.png"
    assert Path(video_path).name == "midform.mp4"
    assert title == "Test Topic Explained"

    assert len(fakes["staging_collector"].calls) == 1
    video_id, midform, shorts, thumb = fakes["staging_collector"].calls[0]
    assert video_id == out.video_id
    assert Path(midform).name == "midform.mp4"
    assert [Path(p).name for p in shorts] == [f"short_{i:02d}.mp4" for i in range(1, 7)]
    assert Path(thumb).name == "thumbnail.png"

    assert len(fakes["exporter"].calls) == 1
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "staging" / out.video_id).exists()
    assert (tmp_path / "pending_review" / out.video_id).exists()


def test_produce_embeds_script_facts_and_metadata(tmp_path):
    fakes = make_fakes(tmp_path)
    producer = VideoProducer(**fakes, work_dir=str(tmp_path / "work"))
    out = producer.produce(completed_result())
    data = out.to_dict()
    assert data["script"]["topic"] == "Test Topic"
    assert data["fact_check"]["topic"] == "Test Topic"
    assert data["metadata"]["title"] == "Test Topic Explained"


@pytest.mark.parametrize("name", list(EXPECTED_STAGE))
def test_step_failure_returns_failed_result_and_keeps_work_dir(name, tmp_path):
    fakes = make_fakes(tmp_path)
    fakes[name] = FailOnCall(fakes[name])
    producer = VideoProducer(**fakes, work_dir=str(tmp_path / "work"))

    out = producer.produce(completed_result())

    assert out.status == "failed"
    assert out.stage == EXPECTED_STAGE[name]
    assert "boom" in out.error
    assert (tmp_path / "work").exists()
    assert not fakes["exporter"].calls
