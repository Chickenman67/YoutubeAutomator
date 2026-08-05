import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from fact_check.fact_checker import FactChecker, FactCheckReport
from metadata.generator import Metadata, MetadataGenerator
from script_generation.generator import ScriptGenerator
from script_generation.schema import Script
from topic_selection.selector import TopicSelector


class Stage(Enum):
    TOPIC_SELECTED = "topic_selected"
    SCRIPT_GENERATED = "script_generated"
    FACTS_CHECKED = "facts_checked"
    METADATA_GENERATED = "metadata_generated"


@dataclass
class PipelineResult:
    topic: str
    stage: Stage
    status: str
    script: Optional[Script] = None
    fact_check: Optional[FactCheckReport] = None
    metadata: Optional[Metadata] = None
    error: Optional[str] = None

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    def to_dict(self) -> Dict[str, Any]:
        data = {"topic": self.topic, "status": self.status, "stage": self.stage.value}
        if self.script is not None:
            data["script"] = self.script.to_dict()
        if self.fact_check is not None:
            data["fact_check"] = self.fact_check.to_dict()
        if self.metadata is not None:
            data["metadata"] = self.metadata.to_dict()
        if self.error is not None:
            data["error"] = self.error
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class PipelineStateMachine:
    def __init__(
        self,
        topic_selector: TopicSelector,
        script_generator: ScriptGenerator,
        fact_checker: FactChecker,
        metadata_generator: MetadataGenerator,
    ):
        self.topic_selector = topic_selector
        self.script_generator = script_generator
        self.fact_checker = fact_checker
        self.metadata_generator = metadata_generator
        self.logger = logging.getLogger(__name__)

    def select_topics(self) -> List[str]:
        try:
            approved = self.topic_selector.select()
            return [topic.topic for topic in approved]
        except Exception as exc:
            self.logger.warning("topic selection failed: %s", exc)
            return []

    def run_video(self, topic: str) -> PipelineResult:
        result = PipelineResult(topic=topic, stage=Stage.TOPIC_SELECTED, status="running")

        try:
            script = self.script_generator.generate_script(topic)
        except Exception as exc:
            return self._fail(result, "script generation", exc)
        result.script = script
        result.stage = Stage.SCRIPT_GENERATED

        try:
            fact_check = self.fact_checker.check_script(script)
        except Exception as exc:
            return self._fail(result, "fact-checking", exc)
        result.fact_check = fact_check
        result.stage = Stage.FACTS_CHECKED

        try:
            metadata = self.metadata_generator.generate_metadata(script)
        except Exception as exc:
            return self._fail(result, "metadata generation", exc)
        result.metadata = metadata
        result.stage = Stage.METADATA_GENERATED
        result.status = "completed"
        return result

    def run_batch(self, topics: Optional[List[str]] = None) -> List[PipelineResult]:
        if topics is None:
            topics = self.select_topics()
        results = []
        for topic in topics:
            results.append(self.run_video(topic))
        return results

    def _fail(self, result: PipelineResult, label: str, exc: Exception) -> PipelineResult:
        result.status = "failed"
        result.error = f"{label} failed: {exc}"
        self.logger.warning("[%s] %s", result.topic, result.error)
        return result
