# Queue Exporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each task below. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `QueueExporter` in `src/pipeline/exporter.py` that turns a staged Video package (the `StagingManifest` from #16) into a `queue/pending_review/{video_id}/` folder: copies every staged asset in, writes a master `metadata.json` combining all video info, fact-check results, and source topic, and logs export completion.

**Architecture:** A new `QueueExporter` takes a `StagingManifest` (injected seam — the output of #16) plus an optional `pending_dir` override. `export()` uses `manifest.video_id` (or an explicit `video_id` override), creates `{pending_dir}/{video_id}/`, copies each manifest asset in, builds a master `metadata.json` from the staged JSON files (source topic from `script.json`, video info from `metadata.json`, fact-check results from `fact_check.json`, plus an `assets` map of the media filenames for the dashboard), and returns an `ExportResult`. A `generate_video_id()` helper (timestamp + short UUID suffix) creates the unique Video ID the pipeline seeds before staging, satisfying the AC.

**Tech Stack:** Python 3.14, stdlib (`dataclasses`, `json`, `shutil`, `uuid`, `datetime`, `logging`, `pathlib`). pytest with temp dirs + dummy files — no re-render, no network, no Manim.

**Design context:** Consumes `StagingManifest` from `src/pipeline/staging.py` (#16). The dashboard (#18) parses `queue/pending_review/{video_id}/` — the exporter guarantees the structure: one folder per Video, 11 video_id-prefixed asset files + one `metadata.json` master. Glossary (`CONTEXT.md`): Queue is the folder-based state system `pending_review/ → approved/ → uploaded/`.

## Global Constraints

- Test runner: `venv\Scripts\python -m pytest -q` (full suite). For one file: `venv\Scripts\python -m pytest tests\test_exporter.py -v`.
- Follow repo conventions: dataclass result object, injected seams, `Path.mkdir(parents=True, exist_ok=True)`, `logging.getLogger(__name__)`, no comments in production code unless asked.
- Repo test convention: `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))` at top of every test file.
- Naming: folder = `{video_id}`; master metadata = `metadata.json`; copied assets keep their staged `{video_id}_*` filenames.
- Master metadata.json shape (parseable by the dashboard):
  ```json
  {
    "video_id": "<id>",
    "topic": "<source topic>",
    "metadata": {"title": ..., "description": ..., "tags": [...], "category": ...},
    "fact_check": {"topic": ..., "results": [...], "low_confidence": [...]},
    "assets": {"midform": "<file>", "shorts": ["<file>", ...], "thumbnail": "<file>"}
  }
  ```

---

### Task 1: generate_video_id + happy-path export

**Files:**
- Create: `src/pipeline/exporter.py`
- Test: `tests/test_exporter.py`

**Interfaces:**
- Produces: `generate_video_id(now=None) -> str` (timestamp + 6-hex-char UUID suffix), `ExportResult` dataclass (`video_id`, `directory`, `assets`, `metadata`), and `QueueExporter.export(manifest, pending_dir=None, video_id=None) -> ExportResult`.

- [ ] **Step 1: Write the failing test**

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
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
    parts = video_id.split("-")
    assert len(parts) == 2
    assert len(parts[0]) == 15
    assert len(parts[1]) == 6


def test_generate_video_ids_are_unique():
    assert generate_video_id() != generate_video_id()


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_exporter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.exporter'`

- [ ] **Step 3: Write minimal implementation**

```python
import json
import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pipeline.staging import StagingManifest


def generate_video_id(now: Optional[datetime] = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


@dataclass
class ExportResult:
    video_id: str
    directory: Path
    assets: List[Path]
    metadata: Path


class QueueExporter:
    def __init__(self, pending_dir: str = "queue/pending_review"):
        self.pending_dir = Path(pending_dir)
        self.logger = logging.getLogger(__name__)

    def export(
        self,
        manifest: StagingManifest,
        pending_dir: Optional[str] = None,
        video_id: Optional[str] = None,
    ) -> ExportResult:
        base = Path(pending_dir) if pending_dir else self.pending_dir
        vid = video_id or manifest.video_id or generate_video_id()
        dest = base / vid
        dest.mkdir(parents=True, exist_ok=True)

        assets = []
        for asset in manifest.assets:
            copied = dest / asset.name
            shutil.copy2(asset, copied)
            assets.append(copied)

        master = dest / "metadata.json"
        master.write_text(self._build_master(manifest, vid), encoding="utf-8")
        self.logger.info("exported video %s to %s", vid, dest)
        return ExportResult(video_id=vid, directory=dest, assets=assets, metadata=master)

    def _build_master(self, manifest: StagingManifest, video_id: str) -> str:
        script = json.loads(manifest.script_file.read_text(encoding="utf-8"))
        metadata = json.loads(manifest.metadata_file.read_text(encoding="utf-8"))
        fact_check = json.loads(manifest.fact_check_file.read_text(encoding="utf-8"))
        master = {
            "video_id": video_id,
            "topic": script.get("topic") or fact_check.get("topic") or "",
            "metadata": metadata,
            "fact_check": fact_check,
            "assets": {
                "midform": manifest.midform.name,
                "shorts": [p.name for p in manifest.shorts],
                "thumbnail": manifest.thumbnail.name,
            },
        }
        return json.dumps(master, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Expected: 4 passed.

### Task 2: video_id override, custom pending dir, logging

**Files:**
- Edit: `src/pipeline/exporter.py`, `tests/test_exporter.py`

**Interfaces:**
- Consumes: `export` from Task 1.
- Produces: `video_id` param overrides `manifest.video_id`; `pending_dir` param overrides the instance default; export completion is logged at INFO with the video id and destination.

- [ ] **Step 1: Write the failing test**

```python
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


def test_export_logs_completion(caplog):
    import logging

    manifest = make_manifest(tmp_path)
    with caplog.at_level(logging.INFO):
        QueueExporter().export(manifest, pending_dir=str(tmp_path / "pending"))
    assert "vid-1" in caplog.text
    assert "exported" in caplog.text
```

- [ ] **Step 2: Run test to verify it fails**

Expected: the override test FAILS because Task-1 `export` always uses `manifest.video_id` and ignores the param? No — Task 1 already implements `vid = video_id or manifest.video_id`, so the override test PASSES. The logging test is the one that needs new behavior.

- [ ] **Step 3: Implement**

The `video_id`/`pending_dir` overrides are already in Task 1. For logging, `export` already calls `self.logger.info(...)` — verify the caplog test captures it (it should pass as-is). Finalize the logging test to assert on the module logger:

```python
def test_export_logs_completion(caplog):
    import logging

    manifest = make_manifest(tmp_path)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        QueueExporter().export(manifest, pending_dir=str(tmp_path / "pending"))
    assert "vid-1" in caplog.text
    assert "exported" in caplog.text
```

- [ ] **Step 4: Run test to verify it passes**

Expected: 8 passed.

### Task 3: Export from pipeline package

**Files:**
- Edit: `src/pipeline/__init__.py`

Add `ExportResult`, `QueueExporter`, `generate_video_id` to the `from .exporter import ...` line and `__all__`.

### Task 4: Full suite, review, commit

- [ ] Run: `venv\Scripts\python -m pytest -q` → all tests pass (existing 180 + 8 new).
- [ ] Code review of `src/pipeline/exporter.py` + `tests/test_exporter.py` (standards + spec).
- [ ] Commit to `master`, push, close #17 with a summary comment (no secrets in messages).
