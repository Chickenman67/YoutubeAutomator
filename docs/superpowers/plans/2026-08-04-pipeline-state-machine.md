# Pipeline State Machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each task below. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `PipelineStateMachine` in `src/pipeline/state_machine.py` that drives a single Video from topic → Script → Fact-Check → Metadata through the four stage values `topic_selected`, `script_generated`, `facts_checked`, `metadata_generated`, returning a complete serializable data package per Video.

**Architecture:** A new `PipelineStateMachine` takes the four upstream modules by **injected seam** (`topic_selector`, `script_generator`, `fact_checker`, `metadata_generator`) — no globals, no network in tests. `run_video(topic)` walks the stages in order, storing rich objects (`Script`, `FactCheckReport`, `Metadata`) on a `PipelineResult` and exposing `to_dict()` for the JSON package. Any stage exception is caught, logged, and the result is marked `failed` with the last-completed stage + error message; `run_batch(topics=None)` loops topics (defaulting to `topic_selector.select()` → `.topic` list) so a failed Video is skipped and production continues to the next topic.

**Tech Stack:** Python 3.14, stdlib `logging`, `enum`, `dataclasses`. pytest with plain fake modules (injected seams) — no network, no Groq/LLM, no Manim.

**Design context:** `docs/spec.md` module layout (topic_selection, script_generation, metadata, queue). Glossary (`CONTEXT.md`): a Video is the unit of production; the state machine produces Script, Fact-Check, and Metadata for it. Video production (render/assemble/stitch/thumbnail) is consumed by the staging collector (#16) — out of scope here. The state machine output (`PipelineResult`) is the "complete data package" #16 consumes.

## Global Constraints

- Test runner: `venv\Scripts\python -m pytest -q` (full suite). For one file: `venv\Scripts\python -m pytest tests\test_state_machine.py -v`.
- Follow repo conventions: injected seams (module objects passed to `__init__`), dataclass result with `to_dict()`, `logging.getLogger(__name__)`, no comments in production code unless asked.
- Repo test convention: `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))` at top of every test file (duplication with `tests/conftest.py` is known and accepted — follow it).
- `Stage` values are exactly: `topic_selected`, `script_generated`, `facts_checked`, `metadata_generated`. `stage` on a result means the **last stage completed** before `status` was set.
- Upstream APIs (verified in this repo): `topic_selector.select() -> list[ApprovedTopic]` (each has `.topic`); `script_generator.generate_script(topic) -> Script`; `fact_checker.check_script(script) -> FactCheckReport`; `metadata_generator.generate_metadata(script) -> Metadata`.

---

### Task 1: Stage enum, PipelineResult, happy-path run_video

**Files:**
- Create: `src/pipeline/state_machine.py`
- Test: `tests/test_state_machine.py`

**Interfaces:**
- Produces: `Stage` enum, `PipelineResult` dataclass (`topic`, `stage`, `status`, `script`, `fact_check`, `metadata`, `error`; `.completed` property; `to_dict()`), and `PipelineStateMachine.run_video(topic) -> PipelineResult`.

- [ ] **Step 1: Write the failing test**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from fact_check.fact_checker import Confidence, FactCheckReport, FactCheckResult
from metadata.generator import Metadata
from pipeline.state_machine import PipelineResult, PipelineStateMachine, Stage
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_state_machine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.state_machine'`

- [ ] **Step 3: Write minimal implementation**

```python
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from fact_check.fact_checker import FactCheckReport
from metadata.generator import Metadata
from script_generation.schema import Script


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


class PipelineStateMachine:
    def __init__(self, topic_selector, script_generator, fact_checker, metadata_generator, logger=None):
        self.topic_selector = topic_selector
        self.script_generator = script_generator
        self.fact_checker = fact_checker
        self.metadata_generator = metadata_generator
        self.logger = logger or logging.getLogger(__name__)

    def run_video(self, topic: str) -> PipelineResult:
        result = PipelineResult(topic=topic, stage=Stage.TOPIC_SELECTED, status="running")
        script = self.script_generator.generate_script(topic)
        result.script = script
        result.stage = Stage.SCRIPT_GENERATED

        fact_check = self.fact_checker.check_script(script)
        result.fact_check = fact_check
        result.stage = Stage.FACTS_CHECKED

        metadata = self.metadata_generator.generate_metadata(script)
        result.metadata = metadata
        result.stage = Stage.METADATA_GENERATED
        result.status = "completed"
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Expected: 3 passed.

### Task 2: Graceful error handling per stage

**Files:**
- Edit: `src/pipeline/state_machine.py`, `tests/test_state_machine.py`

**Interfaces:**
- Consumes: `run_video` from Task 1.
- Produces: on a stage exception, the result is `status="failed"`, `stage` stays at the last completed stage, `error` carries a message, the exception is logged (warning), and later stages are not invoked.

- [ ] **Step 1: Write the failing test**

```python
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
    machine = make_machine(script=script, report=make_report(), metadata_exc=Exception("llm down"))
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
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — exceptions propagate (test errors) because Task-1 `run_video` has no try/except.

- [ ] **Step 3: Implement**

Wrap each stage in its own `try/except Exception`; on failure call a `_fail(result, stage, label, exc)` helper that sets `status="failed"`, `error=f"{label} failed: {exc}"`, logs `logger.warning("[%s] %s", result.topic, result.error)` and returns the result. Labels: `"script generation"`, `"fact-checking"`, `"metadata generation"`.

- [ ] **Step 4: Run test to verify it passes**

Expected: 7 passed.

### Task 3: Batch orchestration with topic skip

**Files:**
- Edit: `src/pipeline/state_machine.py`, `tests/test_state_machine.py`

**Interfaces:**
- Produces: `run_batch(topics: Optional[list[str]] = None) -> list[PipelineResult]`. When `topics` is None, calls `topic_selector.select()` and maps each `ApprovedTopic.topic`; a failing selector logs a warning and returns `[]` (no crash). Each topic runs through `run_video`, so a failed Video is skipped without stopping the batch.

- [ ] **Step 1: Write the failing test**

```python
from topic_selection.selector import ApprovedTopic


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
        topic=topic, source="evergreen", category="science",
        engagement_score=0, explainability_reason="pool",
    )


class FlakyScriptGenerator:
    def __init__(self, script, fail_first=True):
        self.script = script
        self.remaining_failures = 1 if fail_first else 0

    def generate_script(self, topic):
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise ValueError("nope")
        return self.script


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
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — `run_batch` / `select_topics` do not exist (`AttributeError`).

- [ ] **Step 3: Implement**

Add `select_topics()` (calls `self.topic_selector.select()`, maps `.topic`, catches + logs + returns `[]` on error) and `run_batch(topics=None)` (topics = `self.select_topics()` when None; loop `run_video` per topic; return list).

- [ ] **Step 4: Run test to verify it passes**

Expected: 10 passed.

### Task 4: Export from pipeline package

**Files:**
- Create: `src/pipeline/__init__.py`

Export `Stage`, `PipelineResult`, `PipelineStateMachine`.

### Task 5: Full suite, review, commit

- [ ] Run: `venv\Scripts\python -m pytest -q` → all tests pass (existing 159 + 10 new).
- [ ] Code review of `src/pipeline/state_machine.py` + `tests/test_state_machine.py` (standards + spec).
- [ ] Commit to `master`, push, close #15 with a summary comment (no secrets in messages).
