import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from fact_check.fact_checker import Confidence, FactCheckReport, FactCheckResult
from metadata.generator import Metadata
from pipeline.state_machine import PipelineResult, PipelineStateMachine, Stage
from script_generation.schema import Scene, Script
from topic_selection.selector import ApprovedTopic


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


class FakeScriptGenerator:
    def __init__(self, script=None, exc=None):
        self.script = script
        self.exc = exc
        self.called_with = None

    def generate_script(self, topic):
        self.called_with = topic
        if self.exc:
            raise self.exc
        return self.script


class FakeFactChecker:
    def __init__(self, report=None, exc=None):
        self.report = report
        self.exc = exc
        self.called_with = None

    def check_script(self, script):
        self.called_with = script
        if self.exc:
            raise self.exc
        return self.report


class FakeMetadataGenerator:
    def __init__(self, metadata=None, exc=None):
        self.metadata = metadata
        self.exc = exc
        self.called_with = None

    def generate_metadata(self, script):
        self.called_with = script
        if self.exc:
            raise self.exc
        return self.metadata


class FlakyScriptGenerator:
    def __init__(self, script, fail_first=True):
        self.script = script
        self.remaining_failures = 1 if fail_first else 0

    def generate_script(self, topic):
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise ValueError("nope")
        return self.script


class FakeSelector:
    def __init__(self, approved=None, exc=None):
        self.approved = approved or []
        self.exc = exc
        self.calls = 0

    def select(self):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.approved


def make_approved(topic):
    return ApprovedTopic(
        topic=topic,
        source="evergreen",
        category="science",
        engagement_score=0,
        explainability_reason="pool",
    )


def make_machine(
    script=None,
    report=None,
    metadata=None,
    script_exc=None,
    fact_exc=None,
    metadata_exc=None,
):
    return PipelineStateMachine(
        topic_selector=object(),
        script_generator=FakeScriptGenerator(script=script, exc=script_exc),
        fact_checker=FakeFactChecker(report=report, exc=fact_exc),
        metadata_generator=FakeMetadataGenerator(metadata=metadata, exc=metadata_exc),
    )


def test_run_video_reaches_metadata_stage():
    script = make_script()
    machine = make_machine(script=script, report=make_report(), metadata=make_metadata())
    result = machine.run_video("Test Topic")
    assert isinstance(result, PipelineResult)
    assert result.completed
    assert result.status == "completed"
    assert result.stage is Stage.METADATA_GENERATED
    assert result.topic == "Test Topic"
    assert result.error is None


def test_run_video_returns_complete_data_package():
    script = make_script()
    machine = make_machine(script=script, report=make_report(), metadata=make_metadata())
    package = machine.run_video("Test Topic").to_dict()
    assert package["topic"] == "Test Topic"
    assert package["status"] == "completed"
    assert package["stage"] == "metadata_generated"
    assert package["script"]["scenes"]
    assert package["fact_check"]["results"]
    assert package["metadata"]["title"] == "Test Topic Explained"


def test_run_video_calls_stages_in_order():
    script = make_script()
    report = make_report()
    metadata = make_metadata()
    machine = make_machine(script=script, report=report, metadata=metadata)
    machine.run_video("Order Topic")
    assert machine.script_generator.called_with == "Order Topic"
    assert machine.fact_checker.called_with is script
    assert machine.metadata_generator.called_with is script


def test_result_to_json():
    script = make_script("Json Topic")
    machine = make_machine(script=script, report=make_report("Json Topic"), metadata=make_metadata("Json Topic"))
    payload = json.loads(machine.run_video("Json Topic").to_json())
    assert payload["topic"] == "Json Topic"
    assert payload["stage"] == "metadata_generated"
    assert payload["metadata"]["title"] == "Json Topic Explained"


def test_run_video_fails_at_script_generation():
    machine = make_machine(script_exc=ValueError("no script"))
    result = machine.run_video("Bad Topic")
    assert result.status == "failed"
    assert result.stage is Stage.TOPIC_SELECTED
    assert "script" in result.error
    assert machine.fact_checker.called_with is None
    assert machine.metadata_generator.called_with is None


def test_run_video_fails_at_fact_check():
    script = make_script()
    machine = make_machine(script=script, fact_exc=RuntimeError("wikipedia down"))
    result = machine.run_video("Bad Topic")
    assert result.status == "failed"
    assert result.stage is Stage.SCRIPT_GENERATED
    assert "fact" in result.error


def test_run_video_fails_at_metadata():
    script = make_script()
    machine = make_machine(
        script=script, report=make_report(), metadata_exc=Exception("llm down")
    )
    result = machine.run_video("Bad Topic")
    assert result.status == "failed"
    assert result.stage is Stage.FACTS_CHECKED
    assert "metadata" in result.error


def test_run_video_logs_failure(caplog):
    import logging

    machine = make_machine(script_exc=ValueError("boom"))
    with caplog.at_level(logging.WARNING):
        result = machine.run_video("Log Topic")
    assert result.status == "failed"
    assert "boom" in caplog.text


def test_run_batch_skips_failed_topic_and_continues():
    script = make_script()
    machine = PipelineStateMachine(
        topic_selector=object(),
        script_generator=FlakyScriptGenerator(script),
        fact_checker=FakeFactChecker(report=make_report()),
        metadata_generator=FakeMetadataGenerator(metadata=make_metadata()),
    )
    results = machine.run_batch(["Bad Topic", "Good Topic"])
    assert [r.status for r in results] == ["failed", "completed"]
    assert results[0].stage is Stage.TOPIC_SELECTED
    assert results[1].stage is Stage.METADATA_GENERATED


def test_run_batch_uses_selector_when_no_topics():
    selector = FakeSelector(approved=[make_approved("Alpha"), make_approved("Beta")])
    machine = PipelineStateMachine(
        topic_selector=selector,
        script_generator=FakeScriptGenerator(script=make_script()),
        fact_checker=FakeFactChecker(report=make_report()),
        metadata_generator=FakeMetadataGenerator(metadata=make_metadata()),
    )
    results = machine.run_batch()
    assert selector.calls == 1
    assert [r.topic for r in results] == ["Alpha", "Beta"]
    assert all(r.completed for r in results)


def test_run_batch_handles_selector_failure():
    machine = PipelineStateMachine(
        topic_selector=FakeSelector(exc=RuntimeError("feed down")),
        script_generator=FakeScriptGenerator(script=make_script()),
        fact_checker=FakeFactChecker(report=make_report()),
        metadata_generator=FakeMetadataGenerator(metadata=make_metadata()),
    )
    assert machine.run_batch() == []
