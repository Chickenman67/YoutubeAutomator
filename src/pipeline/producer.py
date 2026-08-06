import json
import logging
import shutil
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

        shutil.rmtree(Path(self.work_dir), ignore_errors=True)
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
