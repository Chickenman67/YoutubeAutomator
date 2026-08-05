# CLI Wiring Implementation Plan (#22)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each task below. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the `upload`, `dashboard`, and `generate` subcommands in `src/__main__.py` to the existing modules so the pipeline loop (topic → script → review → upload) is drivable end-to-end from the CLI.

**Architecture:** Move all CLI logic out of `src/__main__.py` into a testable `src/cli.py` with a `main(argv=None)` function; `__main__.py` becomes a thin `sys.exit(main())` wrapper. Each subcommand is a small handler (`cmd_config`, `cmd_upload`, `cmd_dashboard`, `cmd_generate`) plus a `build_state_machine(config)` factory. All heavyweight collaborators (auth, client builder, uploader, dashboard app, state machine) are imported as module-level names so tests monkeypatch them directly. Fatal errors print to stderr and return exit code 1; per-topic generate failures are data (printed as `PipelineResult` JSON, exit 0).

**Tech Stack:** Python 3.14, stdlib `argparse`/`sys`, existing modules `src/config.py`, `src/upload/auth.py`, `src/upload/uploader.py`, `src/dashboard/app.py`, `src/pipeline/state_machine.py`. pytest with monkeypatch — no network, no real OAuth, no real uploads, no Flask server actually started.

**Design context:** Consumes the module surfaces built in #18–#20: `auth.get_credentials(token_path, client_id, client_secret)` + `auth.build_client(credentials)`, `YouTubeUploader.from_config(config, **kwargs)` (kwargs override — `queue_root` and `publish_at` are constructor params), `dashboard.app.create_app(queue_root=...)` with `.run(host, port)`, and `PipelineStateMachine.select_topics()` / `run_video(topic)` returning `PipelineResult`. Config paths use the existing `paths.*` convention already read by `TopicSelector.from_config` (defaults `queue` and `config/youtube_token.json`).

## Global Constraints

- Test runner: `venv\Scripts\python -m pytest -q` (full suite). For one file: `venv\Scripts\python -m pytest tests\test_cli.py -v`.
- Repo test convention: `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))` at top of every test file; per-file helper duplication is the known self-contained-test convention.
- Follow repo conventions: typed injected seams, `Path.mkdir(parents=True, exist_ok=True)`, `logging.getLogger(__name__)`, no comments in production code unless asked.
- Sibling imports are plain absolute from the `src` root (e.g. `from upload.auth import get_credentials`).
- Mock auth, the client builder, the uploader, the dashboard app, and the state machine in every test — zero network, zero real OAuth, zero server startup, zero real uploads.
- `main(argv=None)` — tests pass argv lists; never touch `sys.argv` in tests.
- Exit codes: 0 on success (including a generate run whose per-topic results contain failures — that is data), 1 on fatal errors (missing settings file, `AuthError`, unexpected exception).
- Never log or commit real tokens/credentials.

---

### Task 1: CLI skeleton, `config` command, thin `__main__.py`

**Files:**
- Create: `src/cli.py`
- Modify: `src/__main__.py` (replace body with `sys.exit(main())` wrapper)
- Create: `tests/test_cli.py`

**Interfaces:**
- Produces: `cli.main(argv=None) -> int`, `cli.build_parser()`, `cli.cmd_config(config, args) -> int`. Top-level imports: `get_config` (from `config`), and (for later tasks) `AuthError, build_client, get_credentials` (from `upload.auth`), `YouTubeUploader` (from `upload.uploader`), `create_app` (from `dashboard.app`), `webbrowser`.
- `__main__.py`: `from cli import main; sys.exit(main())`, keeping the existing `sys.path.insert(0, str(Path(__file__).parent))`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
import cli
from cli import main


def write_settings(tmp_path, client_id="", client_secret=""):
    settings = {
        "api_keys": {
            "groq_api_key": "test-key",
            "youtube_client_id": client_id,
            "youtube_client_secret": client_secret,
            "newsapi_api_key": "",
        },
        "topic_split": {"trending_percentage": 0.7, "evergreen_percentage": 0.3, "evergreen_rotation_days": 90},
        "metadata": {"youtube_category_id": 27},
        "upload": {
            "daily_quota_limit": 10000,
            "upload_cost": 1600,
            "default_privacy": "public",
            "retry_attempts": 3,
        },
    }
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(settings), encoding="utf-8")
    return str(p)


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "usage:" in capsys.readouterr().out.lower()


def test_unknown_command_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["bogus"])
    assert exc.value.code == 2


def test_missing_settings_file_returns_1(capsys):
    assert main(["--config", "nope.json", "config"]) == 1
    assert "Settings file not found" in capsys.readouterr().err


def test_config_command_prints_loaded_settings(tmp_path, capsys):
    settings = write_settings(tmp_path)
    assert main(["--config", settings, "config"]) == 0
    out = capsys.readouterr().out
    assert "Configuration loaded successfully" in out
    assert "[Set]" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli'`.

- [ ] **Step 3: Write minimal implementation**

`src/cli.py`:
```python
import argparse
import sys

from config import get_config


def build_parser():
    parser = argparse.ArgumentParser(
        description='YouTube Automation System - Generate educational videos automatically'
    )
    parser.add_argument(
        '--config',
        default='config/settings.json',
        help='Path to settings.json configuration file'
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    subparsers.add_parser('generate', help='Generate scripts for new videos')
    subparsers.add_parser('dashboard', help='Start the review dashboard web interface')
    subparsers.add_parser('upload', help='Upload approved videos to YouTube')
    subparsers.add_parser('config', help='Show current configuration')
    return parser


def cmd_config(config, args):
    print("Configuration loaded successfully:")
    print(f"  Settings file: {config.settings_path}")
    print(f"  Groq API key: {'[Set]' if config.get('api_keys', 'groq_api_key') else '[Missing]'}")
    print(f"  YouTube credentials: {'[Set]' if config.get('api_keys', 'youtube_client_id') else '[Missing]'}")
    print(f"  NewsAPI key: {'[Set]' if config.get('api_keys', 'newsapi_api_key') else '[Missing]'}")
    print(f"  Video target length: {config.get('video', 'target_length_min')}-{config.get('video', 'target_length_max')} minutes")
    print(f"  Scene count: {config.get('video', 'scene_count_min')}-{config.get('video', 'scene_count_max')} scenes")
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    try:
        config = get_config(args.config)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == 'config':
            return cmd_config(config, args)
        if args.command == 'generate':
            return cmd_generate(config, args)
        if args.command == 'dashboard':
            return cmd_dashboard(config, args)
        if args.command == 'upload':
            return cmd_upload(config, args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
```

`src/__main__.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cli import main

if __name__ == '__main__':
    sys.exit(main())
```

Note: `cmd_generate`, `cmd_dashboard`, and `cmd_upload` are referenced by `main` but not yet defined — they are added in Tasks 2–4. To keep the test file green between tasks, add temporary stubs returning 0.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_cli.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/cli.py src/__main__.py tests/test_cli.py
git commit -m "Add testable CLI module with config command (#22)"
```

---

### Task 2: `upload` subcommand

**Files:**
- Modify: `src/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `cli.cmd_upload(config, args) -> int`. Flags on the `upload` subparser: `--queue-root` (default None → `config.get('paths', 'queue_root', default='queue')`), `--publish-at` (default None), `--token-path` (default None → `config.get('paths', 'youtube_token', default='config/youtube_token.json')`).
- Consumes: `get_credentials(token_path, client_id, client_secret)`, `build_client(credentials)`, `YouTubeUploader.from_config(config, client=client, queue_root=..., publish_at=...)` then `.upload_batch()`. Client id/secret come from `config.get('api_keys', 'youtube_client_id')` / `'youtube_client_secret'`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`)

```python
class FakeBatch:
    def to_json(self):
        return json.dumps({"succeeded": [], "failed": [], "skipped": []})


class FakeUploader:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @classmethod
    def from_config(cls, config, **kwargs):
        return cls(**kwargs)

    def upload_batch(self):
        return FakeBatch()


def test_upload_builds_client_and_runs_batch(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "test-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "test-secret")
    captured = {}

    def fake_get_credentials(token_path, client_id, client_secret):
        captured["token_path"] = token_path
        captured["client_id"] = client_id
        captured["client_secret"] = client_secret
        return "creds"

    def fake_build_client(credentials):
        captured["credentials"] = credentials
        return "client"

    monkeypatch.setattr(cli, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(cli, "build_client", fake_build_client)
    monkeypatch.setattr(cli, "YouTubeUploader", FakeUploader)

    assert main(["--config", settings, "upload"]) == 0
    assert captured["token_path"] == "config/youtube_token.json"
    assert captured["client_id"] == "test-id"
    assert captured["client_secret"] == "test-secret"
    assert captured["credentials"] == "creds"
    assert "succeeded" in capsys.readouterr().out


def test_upload_forwards_queue_root_and_publish_at(tmp_path, monkeypatch):
    settings = write_settings(tmp_path)
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "test-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "test-secret")
    captured = {}

    def fake_get_credentials(token_path, client_id, client_secret):
        return "creds"

    monkeypatch.setattr(cli, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(cli, "build_client", lambda creds: "client")
    monkeypatch.setattr(cli, "YouTubeUploader", FakeUploader)

    class FakeUploader2:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        @classmethod
        def from_config(cls, config, **kwargs):
            return cls(**kwargs)

        def upload_batch(self):
            return FakeBatch()

    monkeypatch.setattr(cli, "YouTubeUploader", FakeUploader2)
    assert main([
        "--config", settings, "upload",
        "--queue-root", "my/queue",
        "--publish-at", "2026-08-10T09:00:00Z",
    ]) == 0
    kwargs = captured["kwargs"]
    assert kwargs["queue_root"] == "my/queue"
    assert kwargs["publish_at"] == "2026-08-10T09:00:00Z"
    assert kwargs["client"] == "client"


def test_upload_auth_error_returns_1(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "test-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "test-secret")

    def fail(token_path, client_id, client_secret):
        raise cli.AuthError("no stored token")

    monkeypatch.setattr(cli, "get_credentials", fail)
    assert main(["--config", settings, "upload"]) == 1
    assert "no stored token" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_cli.py -v`
Expected: the new upload tests FAIL (stub `cmd_upload` doesn't exist / returns 0 without calling anything).

- [ ] **Step 3: Write minimal implementation**

Update the top of `src/cli.py` imports and add the subparser flags and handler:

```python
import webbrowser

from upload.auth import AuthError, build_client, get_credentials
from upload.uploader import YouTubeUploader
```

In `build_parser`:
```python
    upload = subparsers.add_parser('upload', help='Upload approved videos to YouTube')
    upload.add_argument('--queue-root', default=None)
    upload.add_argument('--publish-at', default=None, help='ISO datetime to schedule publication (privacy forced to private)')
    upload.add_argument('--token-path', default=None)
```

Handler:
```python
def cmd_upload(config, args):
    token_path = args.token_path or config.get("paths", "youtube_token", default="config/youtube_token.json")
    client_id = config.get("api_keys", "youtube_client_id", default="") or ""
    client_secret = config.get("api_keys", "youtube_client_secret", default="") or ""
    try:
        credentials = get_credentials(token_path, client_id, client_secret)
    except AuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    client = build_client(credentials)
    queue_root = args.queue_root or config.get("paths", "queue_root", default="queue")
    uploader = YouTubeUploader.from_config(
        config, client=client, queue_root=queue_root, publish_at=args.publish_at
    )
    batch = uploader.upload_batch()
    print(batch.to_json())
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_cli.py -v`
Expected: all tests pass (4 from Task 1 + 3 upload).

- [ ] **Step 5: Commit**

```bash
git add src/cli.py tests/test_cli.py
git commit -m "Wire upload subcommand to YouTubeUploader (#22)"
```

---

### Task 3: `dashboard` subcommand

**Files:**
- Modify: `src/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `cli.cmd_dashboard(config, args) -> int`. Flags: `--queue-root` (default None → `config.get('paths', 'queue_root', default='queue')`), `--host` (default `127.0.0.1`), `--port` (default 5000), `--no-browser` (skip `webbrowser.open`).
- Consumes: `create_app(queue_root=...)` from `dashboard.app`, `webbrowser.open(f"http://{host}:{port}")`, then `app.run(host=..., port=...)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`)

```python
class FakeApp:
    def __init__(self):
        self.run_kwargs = None

    def run(self, **kwargs):
        self.run_kwargs = kwargs


def test_dashboard_starts_app_and_opens_browser(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    captured = {}
    fake_app = FakeApp()

    def fake_create_app(queue_root="queue"):
        captured["queue_root"] = queue_root
        return fake_app

    opened = []
    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))

    assert main(["--config", settings, "dashboard"]) == 0
    assert captured["queue_root"] == "queue"
    assert fake_app.run_kwargs == {"host": "127.0.0.1", "port": 5000}
    assert opened == ["http://127.0.0.1:5000"]


def test_dashboard_flags_and_no_browser(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    fake_app = FakeApp()
    opened = []

    monkeypatch.setattr(cli, "create_app", lambda queue_root="queue": fake_app)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))

    assert main([
        "--config", settings, "dashboard",
        "--queue-root", "my/queue", "--host", "0.0.0.0", "--port", "8000", "--no-browser",
    ]) == 0
    assert fake_app.run_kwargs == {"host": "0.0.0.0", "port": 8000}
    assert opened == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_cli.py -v`
Expected: the dashboard tests FAIL (`cmd_dashboard` missing or wrong).

- [ ] **Step 3: Write minimal implementation**

In `build_parser`:
```python
    dashboard = subparsers.add_parser('dashboard', help='Start the review dashboard web interface')
    dashboard.add_argument('--queue-root', default=None)
    dashboard.add_argument('--host', default='127.0.0.1')
    dashboard.add_argument('--port', type=int, default=5000)
    dashboard.add_argument('--no-browser', action='store_true')
```

Handler (add `from dashboard.app import create_app` to cli.py imports):
```python
def cmd_dashboard(config, args):
    queue_root = args.queue_root or config.get("paths", "queue_root", default="queue")
    app = create_app(queue_root=queue_root)
    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        webbrowser.open(url)
    app.run(host=args.host, port=args.port)
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_cli.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/cli.py tests/test_cli.py
git commit -m "Wire dashboard subcommand to review dashboard app (#22)"
```

---

### Task 4: `generate` subcommand

**Files:**
- Modify: `src/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `cli.build_state_machine(config) -> PipelineStateMachine`, `cli.cmd_generate(config, args) -> int`. Flags: `--topic` (default None), `--count` (default 1).
- Consumes: `TopicSelector.from_config(config)`, `GroqClient(api_key=...)`, `ScriptGenerator`, `FactChecker`, `MetadataGenerator`, `PipelineStateMachine`. `cmd_generate` picks topics via `machine.select_topics()[:args.count]` unless `--topic` given, runs `machine.run_video(topic)` per topic, prints each `PipelineResult.to_json()`. Unexpected exceptions (e.g. missing Groq key) bubble to `main` → stderr + return 1.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`)

```python
class FakeMachine:
    def __init__(self, topics=(), raise_on=None):
        self.topics = list(topics)
        self.raise_on = raise_on
        self.ran = []

    def select_topics(self):
        return self.topics

    def run_video(self, topic):
        self.ran.append(topic)
        if self.raise_on:
            raise self.raise_on
        return FakeResult(topic)


class FakeResult:
    def __init__(self, topic):
        self.topic = topic

    def to_json(self):
        return json.dumps({"topic": self.topic, "status": "completed"})


def test_generate_with_explicit_topic(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    machine = FakeMachine(topics=["a", "b", "c"])
    monkeypatch.setattr(cli, "build_state_machine", lambda config: machine)

    assert main(["--config", settings, "generate", "--topic", "Space"]) == 0
    assert machine.ran == ["Space"]
    assert '"topic": "Space"' in capsys.readouterr().out


def test_generate_selects_topics_respecting_count(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    machine = FakeMachine(topics=["a", "b", "c"])
    monkeypatch.setattr(cli, "build_state_machine", lambda config: machine)

    assert main(["--config", settings, "generate", "--count", "2"]) == 0
    assert machine.ran == ["a", "b"]


def test_generate_exception_returns_1(tmp_path, monkeypatch, capsys):
    settings = write_settings(tmp_path)
    machine = FakeMachine(topics=["a"], raise_on=RuntimeError("boom"))
    monkeypatch.setattr(cli, "build_state_machine", lambda config: machine)

    assert main(["--config", settings, "generate"]) == 1
    assert "boom" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python -m pytest tests\test_cli.py -v`
Expected: the generate tests FAIL (`cmd_generate` missing or wrong).

- [ ] **Step 3: Write minimal implementation**

In `build_parser`:
```python
    generate = subparsers.add_parser('generate', help='Generate scripts for new videos')
    generate.add_argument('--topic', default=None, help='Generate for a specific topic instead of selecting')
    generate.add_argument('--count', type=int, default=1, help='Number of topics to process when selecting')
```

Handlers:
```python
def build_state_machine(config):
    from fact_check.fact_checker import FactChecker
    from llm import GroqClient
    from metadata.generator import MetadataGenerator
    from pipeline.state_machine import PipelineStateMachine
    from script_generation.generator import ScriptGenerator
    from topic_selection.selector import TopicSelector

    api_key = config.get("api_keys", "groq_api_key", default="") or ""
    groq = GroqClient(api_key=api_key) if api_key else None
    selector = TopicSelector.from_config(config)
    return PipelineStateMachine(
        topic_selector=selector,
        script_generator=ScriptGenerator(groq),
        fact_checker=FactChecker(),
        metadata_generator=MetadataGenerator(groq),
    )


def cmd_generate(config, args):
    machine = build_state_machine(config)
    if args.topic:
        topics = [args.topic]
    else:
        topics = machine.select_topics()[: args.count]
    for topic in topics:
        result = machine.run_video(topic)
        print(result.to_json())
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python -m pytest tests\test_cli.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/cli.py tests/test_cli.py
git commit -m "Wire generate subcommand to pipeline state machine (#22)"
```

---

### Task 5: Full suite, CLI smoke, review, push, close

- [ ] Run: `venv\Scripts\python -m pytest -q` → all Python tests pass (252 passed / 1 skipped + 12 new).
- [ ] Run: `node --test "tests/dashboard/*.test.mjs"` → JS still 15 passed.
- [ ] CLI smoke (no live upload): `venv\Scripts\python src\__main__.py --help` and `... config` and `... generate --topic "Space"` (will fail fast on missing Groq key only if unset — expected data path).
- [ ] Dashboard smoke: drive `venv\Scripts\python src\__main__.py dashboard --no-browser --port <high>` with playwright per user preference (snapshot/click/console); stop the python process and clean temp dirs afterwards.
- [ ] Two-axis code review (standards + spec) of the diff vs `d7bf050` (handoff fixed point); spawn 2 parallel general sub-agents.
- [ ] Commit any review fixes; push to `master`.
- [ ] Close #22 with a summary comment (no secrets in messages).

---

## Out of scope (explicit)

- Full `generate` video production (render → TTS → stitch → stage → export) — follow-up ticket.
- Live OAuth browser smoke (`auth.run_auth_flow` for real) — separate verification task.
- Changing `config` subcommand output or adding new settings keys to `config/settings.json` (defaults already cover the `paths` reads).
