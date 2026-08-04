import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from topic_selection.pool import EvergreenPool, Topic


def write_pool(path, topics):
    path.write_text(json.dumps({"topics": [t.to_dict() for t in topics]}), encoding="utf-8")


def test_load_topics_from_json(tmp_path):
    p = tmp_path / "evergreen.json"
    write_pool(p, [
        Topic(id=1, text="Roman History", category="History"),
        Topic(id=2, text="Space Exploration", category="Science"),
    ])
    pool = EvergreenPool(p)
    assert len(pool.all_topics()) == 2
    assert pool.all_topics()[0].text == "Roman History"
    assert pool.all_topics()[1].category == "Science"


def test_load_spec_format_topics_wrapper(tmp_path):
    p = tmp_path / "evergreen.json"
    p.write_text(json.dumps({
        "topics": [
            {
                "id": 1,
                "text": "The Fall of the Roman Empire",
                "category": "history",
                "last_used": "2026-05-15",
                "times_used": 2,
            }
        ]
    }), encoding="utf-8")
    pool = EvergreenPool(p, rotation_days=90, now=datetime(2026, 8, 4))
    assert len(pool.all_topics()) == 1
    topic = pool.all_topics()[0]
    assert topic.id == 1
    assert topic.text == "The Fall of the Roman Empire"
    assert topic.category == "history"
    assert topic.times_used == 2


def test_missing_file_returns_empty(tmp_path):
    pool = EvergreenPool(tmp_path / "nope.json")
    assert pool.all_topics() == []


def test_invalid_json_returns_empty(tmp_path):
    p = tmp_path / "evergreen.json"
    p.write_text("this is not json", encoding="utf-8")
    pool = EvergreenPool(p)
    assert pool.all_topics() == []


def test_malformed_entries_skipped_not_crash(tmp_path):
    p = tmp_path / "evergreen.json"
    p.write_text(json.dumps({"topics": [{"id": 1, "text": "ok"}, {"id": "x", "text": "bad"}, "garbage"]}), encoding="utf-8")
    pool = EvergreenPool(p)
    assert [t.text for t in pool.all_topics()] == ["ok"]


def test_save_round_trip(tmp_path):
    p = tmp_path / "evergreen.json"
    pool = EvergreenPool(p)
    pool.topics = [Topic(id=1, text="X", category="C")]
    pool.save()
    loaded = EvergreenPool(p)
    assert loaded.all_topics()[0].text == "X"
    assert loaded.all_topics()[0].category == "C"


def test_available_filters_recently_used(tmp_path):
    now = datetime(2026, 1, 1)
    p = tmp_path / "evergreen.json"
    write_pool(p, [
        Topic(id="1", text="old", last_used=(now - timedelta(days=100)).isoformat()),
        Topic(id="2", text="recent", last_used=(now - timedelta(days=10)).isoformat()),
        Topic(id="3", text="never"),
    ])
    pool = EvergreenPool(p, rotation_days=90, now=now)
    texts = [t.text for t in pool.available_topics()]
    assert set(texts) == {"old", "never"}


def test_rotation_boundary_is_available(tmp_path):
    now = datetime(2026, 1, 1)
    p = tmp_path / "evergreen.json"
    write_pool(p, [Topic(id="1", text="X", last_used=(now - timedelta(days=90)).isoformat())])
    pool = EvergreenPool(p, rotation_days=90, now=now)
    assert [t.text for t in pool.available_topics()] == ["X"]


def test_select_next_updates_and_saves(tmp_path):
    now = datetime(2026, 1, 1)
    p = tmp_path / "evergreen.json"
    write_pool(p, [Topic(id="1", text="A")])
    pool = EvergreenPool(p, rotation_days=90, now=now)
    chosen = pool.select_next()
    assert chosen.text == "A"
    assert chosen.times_used == 1
    assert chosen.last_used == now.isoformat()
    reloaded = EvergreenPool(p, rotation_days=90, now=now)
    assert reloaded.all_topics()[0].times_used == 1
    assert reloaded.all_topics()[0].last_used == now.isoformat()


def test_select_next_none_when_all_recent(tmp_path):
    now = datetime(2026, 1, 1)
    p = tmp_path / "evergreen.json"
    write_pool(p, [Topic(id="1", text="A", last_used=now.isoformat())])
    pool = EvergreenPool(p, rotation_days=90, now=now)
    assert pool.select_next() is None


def test_select_next_none_when_empty(tmp_path):
    pool = EvergreenPool(tmp_path / "missing.json", rotation_days=90)
    assert pool.all_topics() == []
    assert pool.select_next() is None


def test_select_next_prefers_least_recently_used(tmp_path):
    now = datetime(2026, 1, 1)
    p = tmp_path / "evergreen.json"
    write_pool(p, [
        Topic(id="1", text="A", last_used=(now - timedelta(days=200)).isoformat()),
        Topic(id="2", text="B", last_used=(now - timedelta(days=100)).isoformat()),
    ])
    pool = EvergreenPool(p, rotation_days=90, now=now)
    chosen = pool.select_next()
    assert chosen.text == "A"


def test_select_next_prefers_never_used_first(tmp_path):
    now = datetime(2026, 1, 1)
    p = tmp_path / "evergreen.json"
    write_pool(p, [
        Topic(id="1", text="A", last_used=(now - timedelta(days=500)).isoformat()),
        Topic(id="2", text="B"),
    ])
    pool = EvergreenPool(p, rotation_days=90, now=now)
    chosen = pool.select_next()
    assert chosen.text == "B"
