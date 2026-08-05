# Staging Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each task below. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `StagingCollector` in `src/pipeline/staging.py` that gathers a completed Video's package — state machine output (Script, Fact-Check, Metadata) plus video production media (mid-form MP4, one Short MP4 per Scene, thumbnail PNG) — into a staging directory with a consistent `{video_id}_*` naming scheme, validating everything is present, and returns a `StagingManifest` of the collected asset paths.

**Architecture:** A new `StagingCollector` takes the three state-machine outputs and the media file paths by injected seam (file paths + data objects; no globals, no network). `collect()` validates inputs (non-empty `video_id`, non-None data objects, media files exist, Short count == Scene count), creates `{staging_dir}/{video_id}/`, copies the media in with `{video_id}`-prefixed names, writes `metadata.json` / `fact_check.json` / `script.json` from the objects' `to_json()`, and returns a `StagingManifest` whose `.assets` lists every collected path. Missing assets raise; nothing is written until validation passes.

**Tech Stack:** Python 3.14, stdlib (`dataclasses`, `json`, `shutil`, `pathlib`). pytest with temp dirs + dummy media files — no re-render, no network, no Manim.

**Design context:** Consumes the output of #15 (`PipelineResult` objects — but the collector accepts the Script/FactCheckReport/Metadata objects directly to stay decoupled), and the media produced by #9-#13. #17 (queue exporter) will move/copy the staged package into `queue/pending_review/{video_id}/`. Default staging dir is `queue/staging` (transient, created on demand). Glossary (`CONTEXT.md`): a Video is the unit; Shorts are per-Scene.

## Global Constraints

- Test runner: `venv\Scripts\python -m pytest -q` (full suite). For one file: `venv\Scripts\python -m pytest tests\test_staging.py -v`.
- Follow repo conventions: dataclass result with `to_dict()`/`to_json()` + `.assets` convenience, injected seams, `Path.mkdir(parents=True, exist_ok=True)`, no comments in production code unless asked.
- Repo test convention: `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))` at top of every test file (duplication with `tests/conftest.py` is known and accepted — follow it).
- Naming scheme (video_id prefix): `{video_id}_midform.mp4`, `{video_id}_short_{NN}.mp4` (zero-padded scene index), `{video_id}_thumbnail.png`, `{video_id}_metadata.json`, `{video_id}_fact_check.json`, `{video_id}_script.json`.
- Validation order: non-empty `video_id` → `ValueError`; any of script/fact_check/metadata `None` → `ValueError`; **media paths missing → `FileNotFoundError` (checked before the short-count check)**; Short count != Scene count → `ValueError`. No staging directory is created until all validation passes.

---

### Task 1: StagingManifest + happy-path collect

**Files:**
- Create: `src/pipeline/staging.py`
- Test: `tests/test_staging.py`

**Interfaces:**
- Produces: `StagingManifest` dataclass (`video_id`, `directory`, `midform`, `shorts`, `thumbnail`, `metadata_file`, `fact_check_file`, `script_file`; `.assets` property returning every collected path in order; `to_dict()`/`to_json()` with string paths) and `StagingCollector.collect(video_id, script, fact_check, metadata, midform_path, short_paths, thumbnail_path, staging_dir=None) -> StagingManifest`.

- [ ] **Step 1: Write the failing test**

```python
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


def make_media(tmp_path, name, count=6):
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
    assert len(manifest.assets) == 11
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_staging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.staging'`

- [ ] **Step 3: Write minimal implementation**

```python
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from fact_check.fact_checker import FactCheckReport
from metadata.generator import Metadata
from script_generation.schema import Script


@dataclass
class StagingManifest:
    video_id: str
    directory: Path
    midform: Path
    shorts: List[Path]
    thumbnail: Path
    metadata_file: Path
    fact_check_file: Path
    script_file: Path

    @property
    def assets(self) -> List[Path]:
        return [
            self.midform,
            *self.shorts,
            self.thumbnail,
            self.metadata_file,
            self.fact_check_file,
            self.script_file,
        ]

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "directory": str(self.directory),
            "midform": str(self.midform),
            "shorts": [str(p) for p in self.shorts],
            "thumbnail": str(self.thumbnail),
            "metadata_file": str(self.metadata_file),
            "fact_check_file": str(self.fact_check_file),
            "script_file": str(self.script_file),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class StagingCollector:
    def __init__(self, staging_dir: str = "queue/staging"):
        self.staging_dir = Path(staging_dir)

    def collect(
        self,
        video_id: str,
        script: Script,
        fact_check: FactCheckReport,
        metadata: Metadata,
        midform_path: str,
        short_paths: List[str],
        thumbnail_path: str,
        staging_dir: Optional[str] = None,
    ) -> StagingManifest:
        if not video_id:
            raise ValueError("video_id is required")
        if script is None or fact_check is None or metadata is None:
            raise ValueError("script, fact_check, and metadata are required")
        sources = [midform_path, *short_paths, thumbnail_path]
        for path in sources:
            if not Path(path).exists():
                raise FileNotFoundError(f"video asset not found: {path}")
        if len(short_paths) != len(script.scenes):
            raise ValueError(
                f"expected {len(script.scenes)} short videos, got {len(short_paths)}"
            )

        base = Path(staging_dir) if staging_dir else self.staging_dir
        directory = base / video_id
        midform = directory / f"{video_id}_midform.mp4"
        shorts = [
            directory / f"{video_id}_short_{i:02d}.mp4"
            for i in range(1, len(short_paths) + 1)
        ]
        thumbnail = directory / f"{video_id}_thumbnail.png"
        metadata_file = directory / f"{video_id}_metadata.json"
        fact_check_file = directory / f"{video_id}_fact_check.json"
        script_file = directory / f"{video_id}_script.json"

        directory.mkdir(parents=True, exist_ok=True)
        for source, dest in zip(sources, [midform, *shorts, thumbnail]):
            shutil.copy2(source, dest)
        metadata_file.write_text(metadata.to_json(), encoding="utf-8")
        fact_check_file.write_text(fact_check.to_json(), encoding="utf-8")
        script_file.write_text(script.to_json(), encoding="utf-8")

        return StagingManifest(
            video_id=video_id,
            directory=directory,
            midform=midform,
            shorts=shorts,
            thumbnail=thumbnail,
            metadata_file=metadata_file,
            fact_check_file=fact_check_file,
            script_file=script_file,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Expected: 3 passed.

### Task 2: Validation of assets and inputs

**Files:**
- Edit: `src/pipeline/staging.py`, `tests/test_staging.py`

**Interfaces:**
- Consumes: `collect` from Task 1.
- Produces: validation that runs **before** any directory creation or copy: non-empty `video_id` → `ValueError`; any data object `None` → `ValueError`; any media source path missing → `FileNotFoundError`; Short count != Scene count → `ValueError`. No staging directory exists when validation fails.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — Task-1 `collect` has no validation, so `shutil.copy2` raises `FileNotFoundError` for missing files (which would "pass" the missing-file tests) but the `short count`/`None`/`video_id` cases don't raise, and no-asset tests fail.

- [ ] **Step 3: Implement**

At the top of `collect`, before computing dest paths: validate in order (a) `if not video_id: raise ValueError("video_id is required")`; (b) `if script is None or fact_check is None or metadata is None: raise ValueError("script, fact_check, and metadata are required")`; (c) `sources = [midform_path, *short_paths, thumbnail_path]`, then `for path in sources: if not Path(path).exists(): raise FileNotFoundError(f"video asset not found: {path}")`; (d) `if len(short_paths) != len(script.scenes): raise ValueError(f"expected {len(script.scenes)} short videos, got {len(short_paths)}")`. Only then `directory.mkdir(...)`. The media-existence check runs before the short-count check so a genuinely missing file always surfaces as `FileNotFoundError`.

- [ ] **Step 4: Run test to verify it passes**

Expected: 8 passed.

### Task 3: JSON payloads written from objects

**Files:**
- Edit: `tests/test_staging.py` (assertions only, implementation from Task 1 already writes them)

**Interfaces:**
- Produces: `{video_id}_metadata.json`, `{video_id}_fact_check.json`, `{video_id}_script.json` parse as JSON with the expected fields.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

Expected: 10 passed (Task 1 already writes the JSON; the manifest `to_json()` needs to exist).

### Task 4: Export from pipeline package

**Files:**
- Edit: `src/pipeline/__init__.py`

Add `StagingCollector` and `StagingManifest` to the `from .staging import ...` line and `__all__`.

### Task 5: Full suite, review, commit

- [ ] Run: `venv\Scripts\python -m pytest -q` → all tests pass (existing 170 + 10 new).
- [ ] Code review of `src/pipeline/staging.py` + `tests/test_staging.py` (standards + spec).
- [ ] Commit to `master`, push, close #16 with a summary comment (no secrets in messages).
