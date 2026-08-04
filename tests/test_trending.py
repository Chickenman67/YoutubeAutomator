import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from config import Config
from topic_selection.trending import (
    TrendingSelector,
    TrendingTopic,
    dedupe_topics,
    fetch_gdelt,
    fetch_newsapi,
    fetch_wikipedia_pageviews,
    fetch_wikipedia_recent_changes,
    select_by_threshold,
)


def route_get(responses):
    def http_get(url):
        for key, data in responses.items():
            if key in url:
                return data
        raise AssertionError(f"unexpected URL: {url}")
    return http_get


PAGEVIEWS = {
    "pageviews": {
        "items": [
            {
                "project": "en.wikipedia",
                "articles": [
                    {"article": "Earth", "views": 120000, "rank": 1},
                    {"article": "Moon", "views": 90000, "rank": 2},
                    {"article": "Mars", "views": 30000, "rank": 3},
                ],
            }
        ]
    }
}

RECENT_CHANGES = {
    "recentchanges": {
        "query": {
            "recentchanges": [
                {"title": "Earth", "ns": 0},
                {"title": "Planet", "ns": 0},
            ]
        }
    }
}

NEWS = {
    "newsapi": {
        "articles": [
            {"title": "New Space Discovery", "source": {"name": "Example News"}},
            {"title": "Ancient Civilization Found", "source": {"name": "Example News"}},
        ]
    }
}

GDELT = {
    "gdelt": [
        {"title": "Quantum Computing Breakthrough", "url": "http://example.com/q"},
        {"title": "Deep Ocean Secrets", "url": "http://example.com/o"},
    ]
}


def test_pageviews_parse_scores_and_source():
    http_get = route_get(PAGEVIEWS)
    topics = fetch_wikipedia_pageviews(http_get=http_get)
    assert topics[0].text == "Earth"
    assert topics[0].engagement_score == 120000
    assert topics[0].source == "wikipedia"
    assert topics[1].engagement_score == 90000


def test_recent_changes_parse():
    topics = fetch_wikipedia_recent_changes(http_get=route_get(RECENT_CHANGES))
    assert topics[0].text == "Earth"
    assert topics[0].source == "wikipedia"
    assert topics[1].text == "Planet"


def test_newsapi_requires_key_returns_empty():
    topics = fetch_newsapi(api_key="", http_get=route_get(NEWS))
    assert topics == []


def test_newsapi_parses_with_key():
    topics = fetch_newsapi(api_key="secret", http_get=route_get(NEWS))
    assert topics[0].text == "New Space Discovery"
    assert topics[0].source == "newsapi"
    assert len(topics) == 2


def test_gdelt_parses():
    topics = fetch_gdelt(http_get=route_get(GDELT))
    assert topics[0].text == "Quantum Computing Breakthrough"
    assert topics[0].source == "gdelt"
    assert len(topics) == 2


def test_dedupe_keeps_highest_score():
    topics = [
        TrendingTopic(text="Earth", source="wikipedia", engagement_score=90000),
        TrendingTopic(text="Earth", source="newsapi", engagement_score=40000),
        TrendingTopic(text="Moon", source="wikipedia", engagement_score=50000),
    ]
    result = dedupe_topics(topics)
    assert len(result) == 2
    earth = [t for t in result if t.text == "Earth"][0]
    assert earth.engagement_score == 90000


def test_select_lowers_threshold_when_few_topics():
    topics = [
        TrendingTopic(text="A", source="wikipedia", engagement_score=12000),
        TrendingTopic(text="B", source="wikipedia", engagement_score=11000),
        TrendingTopic(text="C", source="wikipedia", engagement_score=10500),
    ]
    selected = select_by_threshold(topics, min_target=3, max_target=10)
    assert len(selected) >= 3


def test_select_keeps_high_threshold_when_many_high():
    topics = [
        TrendingTopic(text=f"T{i}", source="wikipedia", engagement_score=100000)
        for i in range(4)
    ]
    selected = select_by_threshold(topics, min_target=3, max_target=10)
    assert len(selected) == 4


def test_select_raises_when_too_many():
    topics = (
        [TrendingTopic(text=f"H{i}", source="wikipedia", engagement_score=100000) for i in range(10)]
        + [TrendingTopic(text=f"M{i}", source="wikipedia", engagement_score=51000) for i in range(40)]
    )
    selected = select_by_threshold(topics, min_target=3, max_target=10)
    assert len(selected) <= 10
    assert len(selected) >= 3


def test_select_raise_never_returns_zero_with_valid_topics():
    topics = [TrendingTopic(text=f"T{i}", source="wikipedia", engagement_score=10000 + i) for i in range(50)]
    selected = select_by_threshold(topics, min_target=3, max_target=10)
    assert len(selected) > 0


def test_selector_from_config_wires_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWSAPI_API_KEY", "NEWS_KEY")
    settings = {
        "api_keys": {"groq_api_key": "", "youtube_client_id": "", "youtube_client_secret": "", "newsapi_api_key": "NEWS_KEY"},
        "trending": {
            "wikipedia_threshold_high": 80000,
            "wikipedia_threshold_medium": 40000,
            "wikipedia_threshold_low": 20000,
            "min_topics_target": 4,
            "max_topics_target": 12,
            "pageviews_limit": 25,
            "recent_changes_limit": 25,
            "newsapi_query": "space",
            "newsapi_limit": 20,
            "gdelt_query": "a|b",
            "gdelt_limit": 30,
        },
        "topic_split": {}, "video": {}, "production": {}, "metadata": {}, "upload": {},
    }
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(settings), encoding="utf-8")
    selector = TrendingSelector.from_config(Config(str(p)))
    assert selector.min_target == 4
    assert selector.max_target == 12
    assert selector.thresholds == (80000, 40000, 20000)
    names = [name for name, _ in selector.fetchers]
    assert "newsapi" in names


def test_select_empty_returns_empty():
    assert select_by_threshold([], min_target=3, max_target=10) == []


def test_selector_combines_sources_and_tags():
    selector = TrendingSelector(fetchers=[
        ("wikipedia", lambda: fetch_wikipedia_pageviews(http_get=route_get(PAGEVIEWS))),
        ("newsapi", lambda: fetch_newsapi(api_key="k", http_get=route_get(NEWS))),
    ])
    result = selector.fetch()
    sources = {t.source for t in result}
    assert "wikipedia" in sources
    assert "newsapi" in sources


def test_selector_degrades_when_source_fails():
    def broken():
        raise RuntimeError("source down")

    selector = TrendingSelector(fetchers=[
        ("broken", broken),
        ("wikipedia", lambda: fetch_wikipedia_pageviews(http_get=route_get(PAGEVIEWS))),
    ])
    result = selector.fetch()
    assert result
    assert all(t.source == "wikipedia" for t in result)


def test_selector_all_fail_returns_empty():
    def broken():
        raise RuntimeError("down")

    selector = TrendingSelector(fetchers=[("a", broken), ("b", broken)])
    assert selector.fetch() == []


def test_selector_applies_threshold():
    high = [TrendingTopic(text=f"H{i}", source="wikipedia", engagement_score=200000) for i in range(8)]
    low = [TrendingTopic(text=f"L{i}", source="wikipedia", engagement_score=2000) for i in range(8)]
    selector = TrendingSelector(fetchers=[("src", lambda: high + low)])
    result = selector.fetch()
    assert all(t.engagement_score >= 20000 for t in result)
