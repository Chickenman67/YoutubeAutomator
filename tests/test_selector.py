import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import MagicMock
from config import Config
from topic_selection.explainability import ExplainabilityFilter
from topic_selection.pool import EvergreenPool, Topic
from topic_selection.selector import ApprovedTopic, TopicSelector
from topic_selection.trending import TrendingSelector, TrendingTopic


def make_approving_filter():
    client = MagicMock()
    client.generate_json.return_value = {"answer": "Yes", "reason": "Verifiable facts."}
    return ExplainabilityFilter(client)


def make_selector(trending_topics, pool_topics, trending_target=5, evergreen_target=2):
    fetchers = [("wikipedia", lambda: list(trending_topics))]
    trending = TrendingSelector(fetchers=fetchers, min_target=1, max_target=len(trending_topics))
    pool = EvergreenPool(path="__never_written__", rotation_days=90,
                         now=pivoted_now())
    pool.topics = [Topic(**t) for t in pool_topics]
    pool.save = MagicMock()
    return TopicSelector(
        trending_selector=trending,
        explainability_filter=make_approving_filter(),
        evergreen_pool=pool,
        trending_target=trending_target,
        evergreen_target=evergreen_target,
    ), pool


def pivoted_now():
    from datetime import datetime
    return datetime(2026, 5, 1)


def ev_topics(n):
    return [TrendingTopic(text=f"Trending {i}", source="wikipedia",
                          engagement_score=100000, category="science") for i in range(n)]


def pool_topics(n, start=1):
    return [{"id": start + i, "text": f"Evergreen {start + i}", "category": "history",
             "last_used": None, "times_used": 0} for i in range(n)]


def test_output_shape_matches_spec():
    selector, _ = make_selector(ev_topics(5), pool_topics(2))
    first = selector.select()[0]
    assert set(first.to_dict().keys()) == {
        "topic", "source", "category", "engagement_score", "explainability_reason"
    }


def test_output_serializes_to_json():
    selector, _ = make_selector(ev_topics(5), pool_topics(2))
    payload = json.loads(selector.select()[0].to_json())
    assert set(payload.keys()) == {
        "topic", "source", "category", "engagement_score", "explainability_reason"
    }


def test_balanced_split_five_trending_two_evergreen():
    selector, _ = make_selector(ev_topics(5), pool_topics(5))
    result = selector.select()
    assert len(result) == 7
    assert sum(1 for a in result if a.source == "wikipedia") == 5
    assert sum(1 for a in result if a.source == "evergreen") == 2


def test_trending_capped_at_target():
    selector, _ = make_selector(ev_topics(10), pool_topics(10))
    result = selector.select()
    assert sum(1 for a in result if a.source == "wikipedia") == 5
    assert sum(1 for a in result if a.source == "evergreen") == 2


def test_insufficient_trending_increases_evergreen():
    selector, _ = make_selector(ev_topics(3), pool_topics(10))
    result = selector.select()
    assert sum(1 for a in result if a.source == "wikipedia") == 3
    assert sum(1 for a in result if a.source == "evergreen") == 4
    assert len(result) == 7


def test_no_trending_fills_with_evergreen():
    selector, _ = make_selector([], pool_topics(10))
    result = selector.select()
    assert result
    assert all(a.source == "evergreen" for a in result)
    assert len(result) == 7


def test_evergreen_exhausted_gracefully():
    selector, _ = make_selector([], pool_topics(3))
    result = selector.select()
    assert len(result) == 3
    assert all(a.source == "evergreen" for a in result)


def test_order_trending_first_then_evergreen():
    selector, _ = make_selector(ev_topics(3), pool_topics(5))
    result = selector.select()
    sources = [a.source for a in result]
    assert sources[:3] == ["wikipedia"] * 3
    assert sources[3:] == ["evergreen"] * 4


def test_approved_topic_carries_llm_reason():
    selector, _ = make_selector(ev_topics(2), pool_topics(2))
    trending_approved = [a for a in selector.select() if a.source == "wikipedia"]
    assert all(a.explainability_reason == "Verifiable facts." for a in trending_approved)


def test_evergreen_has_pool_category_and_marker_reason():
    selector, _ = make_selector([], pool_topics(2))
    result = selector.select()
    assert all(a.category == "history" for a in result)
    assert all("evergreen" in a.explainability_reason.lower() for a in result)


def test_selector_writes_pool_so_topics_not_reused():
    selector, pool = make_selector(ev_topics(5), pool_topics(2))
    selector.select()
    assert pool.save.called


def test_from_config_wires_split_and_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "K")
    settings = {
        "api_keys": {"groq_api_key": "", "youtube_client_id": "", "youtube_client_secret": "", "newsapi_api_key": ""},
        "trending": {"wikipedia_threshold_high": 50000, "wikipedia_threshold_medium": 20000,
                     "wikipedia_threshold_low": 10000, "min_topics_target": 3, "max_topics_target": 10,
                     "pageviews_limit": 50, "recent_changes_limit": 50,
                     "newsapi_query": "science", "newsapi_limit": 50, "gdelt_query": "a", "gdelt_limit": 50},
        "topic_split": {"trending_percentage": 0.7, "evergreen_percentage": 0.3, "evergreen_rotation_days": 90},
        "video": {}, "production": {}, "metadata": {}, "upload": {},
    }
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(settings), encoding="utf-8")
    selector = TopicSelector.from_config(Config(str(p)))
    assert selector.trending_target == 5
    assert selector.evergreen_target == 2
    assert selector.evergreen_pool.rotation_days == 90
