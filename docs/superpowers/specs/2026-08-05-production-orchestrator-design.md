# Full `generate` Video Production — Orchestrator Design

## Context

`generate` currently stops at the pipeline state machine: it produces script /
fact-check / metadata JSON and prints each `PipelineResult`, but produces no
video assets. The video production modules exist and are individually tested:

- `SceneRenderer.render(scene, output_name, output_dir, width, height)` — Manim
  subprocess per scene.
- `VoiceoverGenerator.generate(scene, output_path)` — Edge TTS voiceover.
- `SceneAssembler.assemble(video_path, audio_path, output_path, width, height)` —
  combines rendered scene + voiceover into a scene clip (audio is the master clock).
- `MidformStitcher.stitch(scene_paths, output_path)` — concatenates landscape
  scene clips with hard cuts into the 1920x1080 master.
- `ThumbnailGenerator.generate(video_path, title, output_path)` — frame +
  title overlay PNG.
- `StagingCollector.collect(...)` — copies assets into `queue/staging/<video_id>/`
  plus `script.json` / `fact_check.json` / `metadata.json`.
- `QueueExporter.export(manifest, pending_dir)` — copies a staging package into
  `queue/pending_review/<video_id>/` and writes the master `metadata.json`.
- `generate_video_id()` — `YYYYMMDD-HHMMSS-<6hex>` id.

ADR-0001 fixes the orientation strategy: the **master is landscape 1920x1080**;
each Scene is **natively re-rendered at 1080x1920** for its Short (never
center-cropped from the master); scene-to-scene transitions in the master are
**hard cuts**. Scenes carry narration audio, so the stitcher concatenates
video+audio together.

This ticket adds the orchestrator that drives these modules end-to-end and wires
it into the `generate` CLI, so one command produces upload-ready assets in
`queue/pending_review/`.

## Decisions (brainstormed, user-approved)

1. **New `src/pipeline/producer.py` module** with a `VideoProducer` class. The
   state machine stays text-only (script/fact-check/metadata) so its tests stay
   fast and network-free; production is a separate seam that consumes a
   `PipelineResult`.
2. **`generate` prints a new `ProductionResult`** per video — one
   JSON-printable object embedding the pipeline data plus export info.
3. **Intermediate files are deleted after a successful export** (work dir and
   staging copy). Failed productions keep their work dir for debugging.
4. **Master resolution is config-driven**: add `production.master_width` /
   `production.master_height` (1920x1080); `production.video_width` /
   `video_height` (1080x1920) remain the Short resolution.
5. **`generate --text-only`** keeps the fast text-only path (state machine only,
   prints `PipelineResult` exactly as today). Default does full production.
6. **Voiceover is generated once per scene** and reused for both the landscape
   and vertical assembly passes (no double TTS).

## Architecture

```
PipelineResult(topic, script, fact_check, metadata)
   └── VideoProducer.produce(result)
        work_dir/<video_id>/
          for each scene i:
             render landscape 1920x1080  -> scene_i_L.mp4
             voiceover (once)            -> voice_i.mp3
             assemble landscape          -> scene_i_L.mp4 (audio master clock)
             render vertical 1080x1920   -> scene_i_V.mp4
             assemble vertical           -> short_i.mp4
          stitch landscape clips         -> midform.mp4   (hard cuts, 1920x1080)
          thumbnail from midform         -> thumbnail.png  (title = metadata.title)
       StagingCollector.collect(...)     -> queue/staging/<video_id>/
       QueueExporter.export(...)         -> queue/pending_review/<video_id>/ + metadata.json
       cleanup work_dir + staging copy
       -> ProductionResult
```

### Component: `VideoProducer` (`src/pipeline/producer.py`)

Constructor takes injected collaborators (repo convention: typed injected seams):

```python
class VideoProducer:
    def __init__(
        self,
        renderer,            # SceneRenderer
        voiceover,           # VoiceoverGenerator
        assembler,           # SceneAssembler
        stitcher,            # MidformStitcher
        thumbnailer,         # ThumbnailGenerator
        staging_collector,   # StagingCollector
        exporter,            # QueueExporter
        short_width: int = 1080,
        short_height: int = 1920,
        master_width: int = 1920,
        master_height: int = 1080,
        fps: int = 30,
        work_dir: str = "queue/work",
        voice: str = DEFAULT_VOICE,
    ): ...

    @classmethod
    def from_config(cls, config, **overrides) -> "VideoProducer": ...
```

`from_config` builds the collaborators from settings (mirrors
`YouTubeUploader.from_config`):

- `master_width/master_height` from `production.master_width/master_height`
  (defaults 1920x1080).
- `short_width/short_height` from `production.video_width/video_height`
  (defaults 1080x1920).
- `fps` from `production.fps` (default 30).
- `work_dir` derived from `paths.queue_root` (`<root>/work`, default
  `queue/work`); staging and pending dirs default to `<root>/staging` and
  `<root>/pending_review`.
- `voice` defaults to `tts.DEFAULT_VOICE` (no new setting; overridable via `**overrides`).
- `**overrides` win over settings (same kwarg-override convention as the
  uploader), so tests and the CLI can pass queue roots / collaborators.

### Component: `ProductionResult`

```python
@dataclass
class ProductionResult:
    topic: str
    status: str                     # "completed" | "failed"
    stage: str                      # "exported" on success; failing step on error
    script: Optional[Script] = None
    fact_check: Optional[FactCheckReport] = None
    metadata: Optional[Metadata] = None
    video_id: Optional[str] = None
    directory: Optional[Path] = None    # pending_review package dir
    assets: List[Path] = ()            # files in the exported package
    metadata_file: Optional[Path] = None
    error: Optional[str] = None

    @property
    def completed(self) -> bool: ...

    def to_dict(self) -> dict: ...     # embeds script/fact_check/metadata dicts
    def to_json(self) -> str: ...      # indent=2, like PipelineResult
```

`produce(result: PipelineResult) -> ProductionResult`:

1. If `result.status != "completed"` → failed `ProductionResult` carrying
   `result.error`, no disk writes.
2. `video_id = generate_video_id()`; `work = work_dir / video_id`;
   `work.mkdir(parents=True, exist_ok=True)`.
3. Per scene `i` (1-based): render landscape `scene_{i}_L.mp4`, generate
   voiceover `voice_{i}.mp3` once, assemble landscape, render vertical
   `scene_{i}_V.mp4`, assemble vertical `short_{i:02d}.mp4`. Output names follow
   the staging/exporter naming (`short_01.mp4`...).
4. Stitch the landscape clips → `midform.mp4`. (Stitcher requires >= 2 scenes —
   a failure to satisfy this surfaces as a production failure, not a crash.)
5. Thumbnail from `midform.mp4` with `metadata.title` → `thumbnail.png`.
6. `staging = staging_collector.collect(video_id, script, fact_check, metadata,
   midform, shorts, thumbnail)`.
7. `export = exporter.export(staging)`.
8. On success only: remove the work dir and the staging copy
   (`staging.directory`), leaving `pending_review/<video_id>/` as the single
   source.
9. Return completed `ProductionResult` (assets = `export.assets`,
   `metadata_file = export.metadata`, `directory = export.directory`).

Any exception during steps 2–8 → failed `ProductionResult` with `stage` = the
failing step label and `error` detail; the work dir is left in place for
debugging.

## CLI changes (`src/cli.py`)

- `generate` subparser gains:
  - `--text-only` (store_true) — run the state machine only and print each
    `PipelineResult.to_json()` (byte-identical to today).
  - `--queue-root` (default None → `config.get("paths", "queue_root", default="queue")`)
    — forwarded to `build_producer`, so a temp-queue smoke works like
    `dashboard`/`upload`.
- `cmd_generate`:
  - `--text-only`: existing loop, `print(result.to_json())`.
  - default: `producer = build_producer(config, queue_root=...)`; per topic →
    `result = machine.run_video(topic)` → `produced = producer.produce(result)`
    → `print(produced.to_json())`.
- New `build_producer(config, queue_root=None)` factory with function-scoped
  imports (same pattern as `build_state_machine`), so CLI tests monkeypatch
  `cli.build_producer`.
- Per-topic failures are data (printed JSON, exit 0); unexpected exceptions
  bubble to `main` → stderr, exit 1. Unchanged.

## Config changes (`config/settings.json`)

Add under `production`:

```json
"master_width": 1920,
"master_height": 1080,
"fps": 30
```

`production.video_width/video_height` (1080x1920) remain the Short resolution.
All reads go through `Config.get(..., default=...)` so existing settings files
keep working. `settings.json` is the only file to update; `Config._load_env_secrets`
is unaffected.

## Error handling

- Non-completed `PipelineResult` → failed `ProductionResult`, no writes.
- Each production step failure → failed `ProductionResult` with the failing step
  (`render` / `voiceover` / `assemble` / `stitch` / `thumbnail` / `stage` /
  `export`) and error detail; work dir retained.
- Cleanup only after successful export.

## Testing

Repo convention: `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))`
at the top of every test file; per-file helper duplication is the known
self-contained-test convention.

### `tests/test_producer.py` (new)

Fake every collaborator; renderers/TTS return tiny synthetic files (created via
`Path.write_bytes`), no Manim subprocess, no real Edge TTS, no moviepy writes
beyond the existing module tests.

- `produce` visits every scene and passes correct per-orientation resolution
  args to renderer and assembler (landscape 1920x1080, vertical 1080x1920).
- Voiceover generated exactly once per scene and reused for both assemblies.
- Stitcher receives landscape clips in scene order; thumbnail called with the
  midform path and `metadata.title`.
- `staging.collect` receives midform/shorts/thumbnail; `exporter.export` called.
- After success: work dir and staging copy removed; pending package intact;
  `ProductionResult` fields (video_id, directory, assets, metadata_file) correct.
- Failure at each step → failed `ProductionResult`, correct `stage` + `error`,
  work dir kept, no export attempted.
- Non-completed `PipelineResult` → failed `ProductionResult`, no disk writes.
- `from_config` reads settings (master/short/fps/voice/paths) and applies
  `**overrides`.

### `tests/test_cli.py` (extend)

- `generate --text-only` prints `PipelineResult.to_json()` and never calls
  `build_producer`.
- Default `generate` builds the producer and prints `ProductionResult.to_json()`;
  `--queue-root` is forwarded to `build_producer`.
- Per-topic production failure → exit 0; unexpected exception → exit 1.
- Monkeypatch `cli.build_state_machine` and `cli.build_producer`.

### Verification

- `venv\Scripts\python -m pytest -q` — full Python suite green.
- `node --test "tests/dashboard/*.test.mjs"` — JS suite still green.
- Optional manual smoke: `generate --topic "<topic>"` against a real Groq key,
  verify all assets land in `queue/pending_review/<video_id>/` and the dashboard
  shows the new video. (Slow: ~2 Manim renders per scene.)

## Out of scope

- Live OAuth upload smoke (separate verification task).
- Real full-render CI (renders stay manual/smoke; unit tests fake the chain).
- Multi-voice / voice-customization settings (voice stays `tts.DEFAULT_VOICE`).
- Parallel render (still one scene at a time).
