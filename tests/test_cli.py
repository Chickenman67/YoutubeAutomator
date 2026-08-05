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


def test_config_command_prints_loaded_settings(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    settings = write_settings(tmp_path)
    assert main(["--config", settings, "config"]) == 0
    out = capsys.readouterr().out
    assert "Configuration loaded successfully" in out
    assert "[Set]" in out


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
