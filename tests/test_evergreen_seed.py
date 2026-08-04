import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from topic_selection.pool import EvergreenPool

SEED_PATH = Path(__file__).parent.parent / 'topics' / 'evergreen.json'

EXPECTED_COUNTS = {
    "history": 30,
    "science": 25,
    "geography": 20,
    "culture": 15,
    "phenomena": 10,
}


def test_seed_file_exists():
    assert SEED_PATH.exists(), f"expected seed file at {SEED_PATH}"


def test_seed_is_valid_schema_and_matches_pool():
    pool = EvergreenPool(path=str(SEED_PATH))
    topics = pool.all_topics()
    assert len(topics) == 100
    for t in topics:
        assert isinstance(t.id, int)
        assert isinstance(t.text, str) and t.text.strip()
        assert t.category in EXPECTED_COUNTS
        assert t.last_used is None
        assert t.times_used == 0


def test_seed_ids_unique():
    pool = EvergreenPool(path=str(SEED_PATH))
    ids = [t.id for t in pool.all_topics()]
    assert len(ids) == len(set(ids))


def test_seed_counts_per_category():
    pool = EvergreenPool(path=str(SEED_PATH))
    counts = {}
    for t in pool.all_topics():
        counts[t.category] = counts.get(t.category, 0) + 1
    assert counts == EXPECTED_COUNTS


def test_seed_filesystem_matches_pool_schema():
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict) and "topics" in data
    topics = data["topics"]
    assert isinstance(topics, list) and len(topics) == 100
    for item in topics:
        assert set(item.keys()) == {"id", "text", "category", "last_used", "times_used"}
        assert isinstance(item["id"], int)
        assert isinstance(item["text"], str) and item["text"].strip()
        assert item["category"] in EXPECTED_COUNTS
        assert item["last_used"] is None
        assert item["times_used"] == 0
