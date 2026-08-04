import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from config import Config, get_config


@pytest.fixture
def settings_file(tmp_path):
    settings = {
        "api_keys": {
            "groq_api_key": "test-key",
            "youtube_client_id": "",
            "youtube_client_secret": "",
            "reddit_client_id": "",
            "reddit_client_secret": "",
            "reddit_user_agent": "YouTubeAutomator/1.0"
        },
        "trending": {
            "wikipedia_threshold_high": 50000,
            "wikipedia_threshold_medium": 20000,
            "wikipedia_threshold_low": 10000,
            "reddit_threshold_high": 5000,
            "reddit_threshold_medium": 2000,
            "reddit_threshold_low": 1000,
            "min_topics_target": 3,
            "max_topics_target": 10
        },
        "topic_split": {
            "trending_percentage": 0.7,
            "evergreen_percentage": 0.3,
            "evergreen_rotation_days": 90
        },
        "video": {
            "target_length_min": 5,
            "target_length_max": 10,
            "scene_count_min": 5,
            "scene_count_max": 7,
            "scene_duration_min": 60,
            "scene_duration_max": 90
        },
        "production": {
            "video_width": 1080,
            "video_height": 1920,
            "thumbnail_width": 1280,
            "thumbnail_height": 720,
            "transition_duration": 1.0
        },
        "metadata": {
            "title_max_length": 60,
            "tag_count_min": 10,
            "tag_count_max": 15,
            "youtube_category_id": 27
        },
        "upload": {
            "daily_quota_limit": 10000,
            "upload_cost": 1600,
            "default_privacy": "public",
            "retry_attempts": 3
        }
    }
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(settings))
    return str(p)


def test_config_loads_settings(settings_file):
    config = Config(settings_file)
    assert config.get('trending', 'wikipedia_threshold_high') == 50000
    assert config.get('upload', 'daily_quota_limit') == 10000


def test_config_get_nested(settings_file):
    config = Config(settings_file)
    assert config.get('topic_split', 'trending_percentage') == 0.7
    assert config.get('metadata', 'youtube_category_id') == 27


def test_config_get_missing_returns_default(settings_file):
    config = Config(settings_file)
    assert config.get('nonexistent', 'key') is None
    assert config.get('nonexistent', 'key', default='fallback') == 'fallback'


def test_config_getitem(settings_file):
    config = Config(settings_file)
    assert config['video']['target_length_min'] == 5


def test_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        Config(str(tmp_path / "does_not_exist.json"))


def test_config_loads_env_secrets(settings_file, monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', 'env-key')
    config = Config(settings_file)
    assert config.get('api_keys', 'groq_api_key') == 'env-key'


def test_get_config_returns_singleton(settings_file):
    c1 = get_config(settings_file)
    c2 = get_config(settings_file)
    assert c1 is c2


def test_get_config_distinguishes_paths(settings_file, tmp_path):
    other = tmp_path / "other.json"
    other.write_text(json.dumps({
        "api_keys": {"groq_api_key": "", "youtube_client_id": "", "youtube_client_secret": "", "reddit_client_id": "", "reddit_client_secret": "", "reddit_user_agent": "a"},
        "trending": {}, "topic_split": {}, "video": {}, "production": {}, "metadata": {}, "upload": {}
    }))
    c1 = get_config(settings_file)
    c2 = get_config(str(other))
    assert c1 is not c2
