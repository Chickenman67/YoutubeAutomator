# Full `generate` Production Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `VideoProducer` that drives the existing video-production modules (render → TTS → assemble → stitch → thumbnail → stage → export) from a `PipelineResult`, and wire it into `generate` so the CLI produces upload-ready assets in `queue/pending_review/`.

**Architecture:** New module `src/pipeline/producer.py` — a `ProductionResult` dataclass (JSON-printable, embeds script/fact-check/metadata plus export info) and a `VideoProducer` class whose constructor takes injected collaborators. Per ADR-0001, each Scene is rendered twice (landscape 1920x1080 for the master, vertical 1080x1920 for the Short), one voiceover per scene is reused for both assemblies, the landscape clips are hard-cut-stitched into `midform.mp4`, a thumbnail is made from the master with `metadata.title`, then `StagingCollector` → `QueueExporter` produce the `pending_review/<video_id>/` package. Work + staging copies are removed only after a successful export. `from_config` builds the collaborators from settings; `cli.cmd_generate` calls `produce()` per topic and prints `ProductionResult.to_json()`; a `--text-only` flag preserves today's fast state-machine-only path.

**Tech Stack:** Python 3.14, pytest + monkeypatch, existing modules `src/pipeline/state_machine.py`, `src/pipeline/staging.py`, `src/pipeline/exporter.py`, `src/video_production/{renderer,tts,assembler,stitcher,thumbnailer}.py`, `src/cli.py`. No network, no Manim subprocess, no Edge TTS, no moviepy writes in producer tests — all collaborators are faked.

## Global Constraints

- Test runner (full suite): `venv\Scripts\python -m pytest -q`. One file: `venv\Scripts\python -m pytest tests\test_producer.py -v`.
- JS suite: `node --test "tests/dashboard/*.test.mjs"` (glob form required on Windows) — must stay green, no changes expected.
- Repo test convention: `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))` at the top of every pytest file; per-file helper duplication is the known self-contained-test convention — reuse the pattern, don't refactor into conftest.py.
- No comments in production code unless asked.
- Sibling imports are plain absolute from the `src` root (e.g. `from pipeline.staging import StagingCollector`).
- Follow repo conventions: typed injected seams, `Path.mkdir(parents=True, exist_ok=True)`, `logging.getLogger(__name__)`.
- Producer module must NOT import Manim/MoviePy/edge-tts at module level. `VideoProducer.__init__` and `from_config` import `DEFAULT_VOICE` inside the function body (function-scoped), keeping `import pipeline.producer` light.
- Never log or commit real tokens/credentials.
- Python 3.14 gotcha: any test fake that replaces a classmethod must use `@classmethod` (a plain function assigned to a class attribute no longer binds `cls`).

---

### Task 1: `ProductionResult` + `VideoProducer` skeleton

**Files:**
- Create: `src/pipeline/producer.py`
- Create: `tests/test_producer.py`

**Interfaces:**
- Produces: `pipeline.producer.ProductionResult` (dataclass with `.topic`, `.status`, `.stage`, optional `.script`/`.fact_check`/`.metadata`/`.video_id`/`.directory`/`.assets`/`.metadata_file`/`.error`, plus `.completed`, `.to_dict()`, `.to_json()`), `pipeline.producer.VideoProducer` (constructor with the 7 injected collaborators + `short_width/short_height/master_width/master_height/fps/work_dir/voice`; `produce(result) -> ProductionResult` handles the non-completed pipeline result now, raises `NotImplementedError` for completed results until Task 2).
- Consumes: `PipelineResult` from `pipeline.state_machine` (`.topic`, `.status`, `.error`, `.script`, `.fact_check`, `.metadata`), `Script` from `script_generation.schema`, `FactCheckReport` from `fact_check.fact_checker`, `Metadata` from `metadata.generator`.

- [ ] **Step 1: Write the failing tests**

`tests/test_producer.py`:

```python
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
    assert data["directory"] == "q/pending_review/v1"
    assert data["assets"] == ["a.mp4"]
    assert data["metadata_file"] == "q/pending_review/v1/metadata.json"
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_producer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.producer'`.

- [ ] **Step 3: Write minimal implementation**

`src/pipeline/producer.py`:

```python
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from fact_check.fact_checker import FactCheckReport
from metadata.generator import Metadata
from pipeline.exporter import generate_video_id
from pipeline.state_machine import PipelineResult
from script_generation.schema import Script


class _ProductionStepFailed(Exception):
    def __init__(self, stage: str, original: Exception):
        super().__init__(stage)
        self.stage = stage
        self.original = original


@dataclass
class ProductionResult:
    topic: str
    status: str
    stage: str
    script: Optional[Script] = None
    fact_check: Optional[FactCheckReport] = None
    metadata: Optional[Metadata] = None
    video_id: Optional[str] = None
    directory: Optional[Path] = None
    assets: List[Path] = field(default_factory=list)
    metadata_file: Optional[Path] = None
    error: Optional[str] = None

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    def to_dict(self) -> Dict[str, Any]:
        data = {"topic": self.topic, "status": self.status, "stage": self.stage}
        if self.script is not None:
            data["script"] = self.script.to_dict()
        if self.fact_check is not None:
            data["fact_check"] = self.fact_check.to_dict()
        if self.metadata is not None:
            data["metadata"] = self.metadata.to_dict()
        if self.video_id is not None:
            data["video_id"] = self.video_id
        if self.directory is not None:
            data["directory"] = str(self.directory)
        if self.assets:
            data["assets"] = [str(p) for p in self.assets]
        if self.metadata_file is not None:
            data["metadata_file"] = str(self.metadata_file)
        if self.error is not None:
            data["error"] = self.error
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class VideoProducer:
    def __init__(
        self,
        renderer,
        voiceover,
        assembler,
        stitcher,
        thumbnailer,
        staging_collector,
        exporter,
        short_width: int = 1080,
        short_height: int = 1920,
        master_width: int = 1920,
        master_height: int = 1080,
        fps: int = 30,
        work_dir: str = "queue/work",
        voice: Optional[str] = None,
    ):
        from video_production import DEFAULT_VOICE

        self.renderer = renderer
        self.voiceover = voiceover
        self.assembler = assembler
        self.stitcher = stitcher
        self.thumbnailer = thumbnailer
        self.staging_collector = staging_collector
        self.exporter = exporter
        self.short_width = short_width
        self.short_height = short_height
        self.master_width = master_width
        self.master_height = master_height
        self.fps = fps
        self.work_dir = work_dir
        self.voice = voice or DEFAULT_VOICE
        self.logger = logging.getLogger(__name__)

    def produce(self, result: PipelineResult) -> ProductionResult:
        if result.status != "completed":
            return ProductionResult(
                topic=result.topic,
                status="failed",
                stage="pipeline",
                error=result.error or "pipeline did not complete",
                script=result.script,
                fact_check=result.fact_check,
                metadata=result.metadata,
            )
        raise NotImplementedError("completed-path produce() is implemented in the next task")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_producer.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/producer.py tests/test_producer.py
git commit -m "Add ProductionResult type and VideoProducer skeleton"
```

---

### Task 2: `produce()` full implementation

**Files:**
- Modify: `src/pipeline/producer.py` (replace the `raise NotImplementedError` line with the full flow)
- Modify: `tests/test_producer.py` (append tests)

**Interfaces:**
- Consumes: the collaborators' exact call signatures — `renderer.render(scene, output_name, output_dir, width=..., height=..., fps=...) -> RenderResult(path,...)`, `voiceover.generate(scene, output_path, voice=...) -> VoiceoverResult(path,...)`, `assembler.assemble(video_path, audio_path, output_path, width=..., height=..., fps=...) -> AssemblyResult(path,...)`, `stitcher.stitch(scene_paths, output_path, width=..., height=..., fps=...) -> StitchResult(path,...)`, `thumbnailer.generate(video_path, title, output_path) -> ThumbnailResult(path,...)`, `staging_collector.collect(video_id, script, fact_check, metadata, midform_path, short_paths, thumbnail_path) -> StagingManifest(directory,...)`, `exporter.export(manifest) -> ExportResult(video_id, directory, assets, metadata)`.
- Produces: `VideoProducer.produce(result) -> ProductionResult` for completed results: work dir per video; per scene render landscape `scene_{i}_L` then vertical `scene_{i}_V`; one voiceover `voice_{i}.mp3` reused for both assemblies; landscape clips `scene_{i}_L.mp4` stitched to `midform.mp4`; `thumbnail.png` from midform with `metadata.title`; staged then exported; work + staging removed on success; `ProductionResult(status="completed", stage="exported", ...)`. On any step failure: `ProductionResult(status="failed", stage=<step>)` with error `"<step> failed: <exc>"`, work dir kept, no export.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_producer.py`)

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_producer.py -v`
Expected: the 3 existing tests pass; the new tests FAIL with `NotImplementedError`.

- [ ] **Step 3: Write minimal implementation**

In `src/pipeline/producer.py`, add `import shutil` to the module-level imports (next to `import json`), replace the `raise NotImplementedError(...)` line and add the helpers:

```python
    def produce(self, result: PipelineResult) -> ProductionResult:
        if result.status != "completed":
            return ProductionResult(
                topic=result.topic,
                status="failed",
                stage="pipeline",
                error=result.error or "pipeline did not complete",
                script=result.script,
                fact_check=result.fact_check,
                metadata=result.metadata,
            )

        video_id = generate_video_id()
        work = Path(self.work_dir) / video_id
        work.mkdir(parents=True, exist_ok=True)

        shorts: List[Path] = []
        landscape: List[Path] = []
        try:
            for i, scene in enumerate(result.script.scenes, start=1):
                landscape_raw = self._step("render", lambda: self.renderer.render(
                    scene, f"scene_{i}_L", str(work),
                    width=self.master_width, height=self.master_height, fps=self.fps,
                ))
                voiceover = self._step("voiceover", lambda: self.voiceover.generate(
                    scene, str(work / f"voice_{i}.mp3"), voice=self.voice,
                ))
                scene_landscape = self._step("assemble", lambda: self.assembler.assemble(
                    str(landscape_raw.path), str(voiceover.path), str(work / f"scene_{i}_L.mp4"),
                    width=self.master_width, height=self.master_height, fps=self.fps,
                ))
                landscape.append(scene_landscape.path)
                vertical_raw = self._step("render", lambda: self.renderer.render(
                    scene, f"scene_{i}_V", str(work),
                    width=self.short_width, height=self.short_height, fps=self.fps,
                ))
                short = self._step("assemble", lambda: self.assembler.assemble(
                    str(vertical_raw.path), str(voiceover.path), str(work / f"short_{i:02d}.mp4"),
                    width=self.short_width, height=self.short_height, fps=self.fps,
                ))
                shorts.append(short.path)

            midform = self._step("stitch", lambda: self.stitcher.stitch(
                [str(p) for p in landscape], str(work / "midform.mp4"),
                width=self.master_width, height=self.master_height, fps=self.fps,
            ))
            thumbnail = self._step("thumbnail", lambda: self.thumbnailer.generate(
                str(midform.path), result.metadata.title, str(work / "thumbnail.png"),
            ))
            staging = self._step("stage", lambda: self.staging_collector.collect(
                video_id, result.script, result.fact_check, result.metadata,
                str(midform.path), [str(p) for p in shorts], str(thumbnail.path),
            ))
            export = self._step("export", lambda: self.exporter.export(staging))
        except _ProductionStepFailed as exc:
            return self._fail(result, exc)

        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(staging.directory, ignore_errors=True)

        return ProductionResult(
            topic=result.topic,
            status="completed",
            stage="exported",
            script=result.script,
            fact_check=result.fact_check,
            metadata=result.metadata,
            video_id=video_id,
            directory=export.directory,
            assets=export.assets,
            metadata_file=export.metadata,
        )

    def _step(self, stage: str, fn):
        try:
            return fn()
        except Exception as exc:
            raise _ProductionStepFailed(stage, exc) from exc

    def _fail(self, result: PipelineResult, exc: _ProductionStepFailed) -> ProductionResult:
        message = f"{exc.stage} failed: {exc.original}"
        self.logger.warning("[%s] %s", result.topic, message)
        return ProductionResult(
            topic=result.topic,
            status="failed",
            stage=exc.stage,
            error=message,
            script=result.script,
            fact_check=result.fact_check,
            metadata=result.metadata,
        )
```

Note: `renderer.render` returns a `RenderResult` whose `.path` is the Manim-produced file under `<work>/media/`, so `scene_{i}_L.mp4` (assembled output at `work/`) does not collide with the raw render at `work/media/scene_{i}_L.mp4`.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_producer.py -v`
Expected: all tests pass (3 from Task 1 + 4 new: happy path, embedded data, 7 parametrized failures).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/producer.py tests/test_producer.py
git commit -m "Implement VideoProducer.produce end-to-end with per-step failure handling"
```

---

### Task 3: `from_config` + settings keys

**Files:**
- Modify: `src/pipeline/producer.py` (add `from_config` classmethod)
- Modify: `config/settings.json` (add `master_width`, `master_height`, `fps` under `production`)
- Modify: `tests/test_producer.py` (append tests)

**Interfaces:**
- Produces: `VideoProducer.from_config(config, queue_root=None, **overrides) -> VideoProducer` — reads `production.master_width/master_height` (defaults 1920x1080), `production.video_width/video_height` (defaults 1080x1920), `production.fps` (default 30); derives `work_dir = <root>/work`, staging = `<root>/staging`, pending = `<root>/pending_review` from `queue_root` or `paths.queue_root` (default `queue`); voice = `DEFAULT_VOICE`; `**overrides` win over every constructor kwarg.
- Consumes: `Config.get(*keys, default=...)` from `src/config.py`; the real lightweight constructors `SceneRenderer`, `VoiceoverGenerator`, `SceneAssembler`, `MidformStitcher`, `ThumbnailGenerator`, `StagingCollector(staging_dir=...)`, `QueueExporter(pending_dir=...)` (all cheap to construct — no I/O until a method is called).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_producer.py`)

```python
from config import Config


def write_producer_settings(tmp_path, extra=None):
    settings = {
        "api_keys": {
            "groq_api_key": "", "youtube_client_id": "",
            "youtube_client_secret": "", "newsapi_api_key": "",
        },
        "production": {
            "video_width": 1080, "video_height": 1920,
            "master_width": 1920, "master_height": 1080, "fps": 30,
        },
    }
    if extra:
        settings.update(extra)
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(settings), encoding="utf-8")
    return Config(str(p))


def test_from_config_reads_settings_and_paths(tmp_path):
    config = write_producer_settings(tmp_path, extra={"paths": {"queue_root": "my/queue"}})
    producer = VideoProducer.from_config(config)
    assert producer.master_width == 1920
    assert producer.master_height == 1080
    assert producer.short_width == 1080
    assert producer.short_height == 1920
    assert producer.fps == 30
    assert producer.work_dir == "my/queue/work"
    assert str(producer.staging_collector.staging_dir) == "my/queue/staging"
    assert str(producer.exporter.pending_dir) == "my/queue/pending_review"


def test_from_config_defaults_when_keys_missing(tmp_path):
    config = write_producer_settings(tmp_path, extra={"production": {}})
    producer = VideoProducer.from_config(config)
    assert producer.master_width == 1920
    assert producer.master_height == 1080
    assert producer.short_width == 1080
    assert producer.short_height == 1920
    assert producer.fps == 30
    assert producer.work_dir == "queue/work"


def test_from_config_queue_root_override(tmp_path):
    config = write_producer_settings(tmp_path)
    producer = VideoProducer.from_config(config, queue_root="other/root")
    assert producer.work_dir == "other/root/work"
    assert str(producer.staging_collector.staging_dir) == "other/root/staging"
    assert str(producer.exporter.pending_dir) == "other/root/pending_review"


def test_from_config_overrides_win(tmp_path):
    config = write_producer_settings(tmp_path)
    producer = VideoProducer.from_config(config, voice="en-US-AriaNeural", fps=60)
    assert producer.voice == "en-US-AriaNeural"
    assert producer.fps == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_producer.py -v`
Expected: the 4 new tests FAIL with `TypeError: from_config() missing...` / `AttributeError: from_config`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/pipeline/producer.py` (inside `VideoProducer`):

```python
    @classmethod
    def from_config(cls, config, queue_root: Optional[str] = None, **overrides):
        from video_production import (
            DEFAULT_VOICE,
            MidformStitcher,
            SceneAssembler,
            SceneRenderer,
            ThumbnailGenerator,
            VoiceoverGenerator,
        )

        root = queue_root or config.get("paths", "queue_root", default="queue")
        master_width = config.get("production", "master_width", default=1920)
        master_height = config.get("production", "master_height", default=1080)
        short_width = config.get("production", "video_width", default=1080)
        short_height = config.get("production", "video_height", default=1920)
        fps = config.get("production", "fps", default=30)

        return cls(
            renderer=SceneRenderer(width=master_width, height=master_height, fps=fps),
            voiceover=VoiceoverGenerator(),
            assembler=SceneAssembler(width=master_width, height=master_height, fps=fps),
            stitcher=MidformStitcher(width=master_width, height=master_height, fps=fps),
            thumbnailer=ThumbnailGenerator(),
            staging_collector=StagingCollector(staging_dir=f"{root}/staging"),
            exporter=QueueExporter(pending_dir=f"{root}/pending_review"),
            short_width=short_width,
            short_height=short_height,
            master_width=master_width,
            master_height=master_height,
            fps=fps,
            work_dir=f"{root}/work",
            voice=DEFAULT_VOICE,
            **overrides,
        )
```

Add the staging/exporter collaborators to the existing `producer.py` module imports (`pipeline.exporter` is already imported for `generate_video_id`):

```python
from pipeline.exporter import QueueExporter, generate_video_id
from pipeline.staging import StagingCollector
```

Update `config/settings.json` under `production`:

```json
  "production": {
    "video_width": 1080,
    "video_height": 1920,
    "thumbnail_width": 1280,
    "thumbnail_height": 720,
    "transition_duration": 1.0,
    "master_width": 1920,
    "master_height": 1080,
    "fps": 30
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_producer.py tests\test_config.py -v`
Expected: all producer tests pass; `test_config.py` still passes (settings additions are additive).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/producer.py config/settings.json tests/test_producer.py
git commit -m "Add VideoProducer.from_config and master-resolution settings"
```

---

### Task 4: CLI wiring

**Files:**
- Modify: `src/cli.py` (generate subparser flags; `cmd_generate`; new `build_producer`)
- Modify: `tests/test_cli.py` (update 3 existing generate tests; append new tests)

**Interfaces:**
- Produces: `cli.build_producer(config, queue_root=None) -> VideoProducer` (function-scoped `from pipeline.producer import VideoProducer`), `cmd_generate(config, args)` handling `--text-only` (print `PipelineResult.to_json()`, never build the producer) vs full production (build producer, print `ProductionResult.to_json()`), plus `--queue-root` forwarded to `build_producer`.
- Consumes: `VideoProducer.from_config(config, queue_root=...)`, `PipelineResult.to_json()`, `ProductionResult.to_json()`.

- [ ] **Step 1: Update the 3 existing generate tests to use `--text-only`**

In `tests/test_cli.py`, add `--text-only` to these calls (the FakeMachine results lack `status`/`script` so the full path would crash on them — they test topic selection, which `--text-only` preserves byte-for-byte):

- `test_generate_with_explicit_topic`: `main(["--config", settings, "generate", "--topic", "Space", "--text-only"])`
- `test_generate_selects_topics_respecting_count`: `main(["--config", settings, "generate", "--count", "2", "--text-only"])`
- `test_generate_exception_returns_1`: `main(["--config", settings, "generate", "--text-only"])`

Run: `venv\Scripts\python -m pytest tests\test_cli.py -v`
Expected: existing tests still pass (behavior unchanged).

- [ ] **Step 2: Write the failing new tests** (append to `tests/test_cli.py`)

```python
def test_generate_full_path_produces_and_prints(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    machine = FakeMachine(topics=["Space"])
    monkeypatch.setattr(cli, "build_state_machine", lambda config: machine)
    captured = {}

    class FakeProduced:
        def to_json(self):
            return json.dumps({"topic": "Space", "status": "completed", "stage": "exported"})

    class FakeProducer:
        def __init__(self, queue_root=None):
            captured["queue_root"] = queue_root

        def produce(self, result):
            captured["produced_topic"] = result.topic
            return FakeProduced()

    monkeypatch.setattr(cli, "build_producer", lambda config, queue_root=None: FakeProducer(queue_root))

    assert main(["--config", settings, "generate", "--topic", "Space"]) == 0
    assert captured["queue_root"] is None
    assert captured["produced_topic"] == "Space"
    assert '"stage": "exported"' in capsys.readouterr().out


def test_generate_forwards_queue_root_to_producer(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    machine = FakeMachine(topics=["a"])
    monkeypatch.setattr(cli, "build_state_machine", lambda config: machine)
    captured = {}

    class FakeProducer:
        def __init__(self, queue_root=None):
            captured["queue_root"] = queue_root

        def produce(self, result):
            return FakeResult(result.topic)

    monkeypatch.setattr(cli, "build_producer", lambda config, queue_root=None: FakeProducer(queue_root))

    assert main(["--config", settings, "generate", "--queue-root", "my/queue"]) == 0
    assert captured["queue_root"] == "my/queue"


def test_generate_text_only_never_builds_producer(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    machine = FakeMachine(topics=["a", "b"])
    monkeypatch.setattr(cli, "build_state_machine", lambda config: machine)
    built = []

    def fail_if_built(config, queue_root=None):
        built.append(queue_root)
        raise AssertionError("producer should not be built in text-only mode")

    monkeypatch.setattr(cli, "build_producer", fail_if_built)

    assert main(["--config", settings, "generate", "--count", "2", "--text-only"]) == 0
    assert machine.ran == ["a", "b"]
    assert built == []


def test_generate_production_failure_is_data_exit_0(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    machine = FakeMachine(topics=["a"])
    monkeypatch.setattr(cli, "build_state_machine", lambda config: machine)

    class FailedProduced:
        def to_json(self):
            return json.dumps({"topic": "a", "status": "failed", "stage": "render", "error": "boom"})

    class FakeProducer:
        def produce(self, result):
            return FailedProduced()

    monkeypatch.setattr(cli, "build_producer", lambda config, queue_root=None: FakeProducer())

    assert main(["--config", settings, "generate", "--topic", "a"]) == 0
    assert '"status": "failed"' in capsys.readouterr().out
```

- [ ] **Step 3: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_cli.py -v`
Expected: the 4 new tests FAIL (no `--text-only` flag / no `build_producer`).

- [ ] **Step 4: Write minimal implementation**

In `src/cli.py`, update the `generate` subparser:

```python
    generate = subparsers.add_parser('generate', help='Generate scripts and videos for new topics')
    generate.add_argument('--topic', default=None, help='Generate for a specific topic instead of selecting')
    generate.add_argument('--count', type=int, default=1, help='Number of topics to process when selecting')
    generate.add_argument('--text-only', action='store_true', help='Stop after script/fact-check/metadata; skip video production')
    generate.add_argument('--queue-root', default=None, help='Root of the queue directory for staging and pending review (default: paths.queue_root -> queue)')
```

Replace `cmd_generate` and add `build_producer`:

```python
def cmd_generate(config, args):
    machine = build_state_machine(config)
    if args.topic:
        topics = [args.topic]
    else:
        topics = machine.select_topics()[: args.count]
    if args.text_only:
        for topic in topics:
            print(machine.run_video(topic).to_json())
        return 0
    producer = build_producer(config, queue_root=args.queue_root)
    for topic in topics:
        result = machine.run_video(topic)
        print(producer.produce(result).to_json())
    return 0


def build_producer(config, queue_root=None):
    from pipeline.producer import VideoProducer
    return VideoProducer.from_config(config, queue_root=queue_root)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_cli.py tests\test_producer.py -v`
Expected: all pass.

- [ ] **Step 6: CLI smoke**

Run:
```
venv\Scripts\python src\__main__.py --help
venv\Scripts\python src\__main__.py generate --help
venv\Scripts\python src\__main__.py generate --topic "Space" --text-only
```
Expected: help output lists `--text-only` / `--queue-root`; the `--text-only` run prints `PipelineResult` JSON (data path — exits 0 even if a step fails on a missing Groq key).

- [ ] **Step 7: Commit**

```bash
git add src/cli.py tests/test_cli.py
git commit -m "Wire full video production into generate with text-only escape hatch"
```

---

### Task 5: Full verification, review, push, close

- [ ] **Step 1: Full Python suite**

Run: `venv\Scripts\python -m pytest -q`
Expected: all pass (previous baseline 266 passed / 1 skipped + new producer/cli tests).

- [ ] **Step 2: JS suite**

Run: `node --test "tests/dashboard/*.test.mjs"`
Expected: 15 passed.

- [ ] **Step 3: Create the tracking issue** (if not already created)

```bash
gh issue create --title "Full generate video production orchestrator" --body "Wire render → TTS → assemble → stitch → thumbnail → stage → export into generate (VideoProducer). Spec: docs/superpowers/specs/2026-08-05-production-orchestrator-design.md. Plan: docs/superpowers/plans/2026-08-05-production-orchestrator.md."
```
Record its number (expected `#23`).

- [ ] **Step 4: Optional real render smoke** (manual; slow)

Run: `venv\Scripts\python src\__main__.py generate --topic "<topic>"` with a real Groq key. Expect ~2 Manim renders per scene (~10+ min for 6 scenes). Verify `queue/pending_review/<video_id>/` contains `midform.mp4`, `short_01.mp4`..`short_06.mp4`, `thumbnail.png`, `metadata.json`, `*_script.json`, `*_fact_check.json`, and that `queue/work/` and `queue/staging/` contain no leftover `<video_id>` dir. If the render is too slow, skip this step and note it in the issue.

- [ ] **Step 5: Two-axis code review**

Fixed point: `d596b15` (the spec commit). Dispatch 2 parallel `general` sub-agents — one reviewing standards, one reviewing spec-vs-implementation (see superpowers:code-review). Fix findings in follow-up commits.

- [ ] **Step 6: Final verification + push + close**

Run both suites again, then:
```bash
git push
```
Close the issue with a summary comment (no secrets in the body): `gh issue close <n> --comment "<summary>"`.

---

## Out of scope (explicit)

- Live OAuth upload smoke (separate verification task).
- Parallel rendering / render caching (still one scene at a time).
- Real full-render CI (renders stay manual/smoke; unit tests fake the chain).
- Multi-voice / voice-customization settings (voice stays `tts.DEFAULT_VOICE`).
- Changes to the review dashboard, uploader, or state machine behavior.
