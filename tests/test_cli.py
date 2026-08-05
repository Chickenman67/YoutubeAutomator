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
