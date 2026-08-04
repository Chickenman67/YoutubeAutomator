import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Any, List, Optional, Tuple

WIKIPEDIA_USER_AGENT = "YoutubeAutomator/0.1"

PAGEVIEWS_LIMIT = 50
RECENT_CHANGES_LIMIT = 50
NEWSAPI_LIMIT = 50
GDELT_LIMIT = 50
NEWSAPI_QUERY = "science"
GDELT_QUERY = "science|history|space"
DEFAULT_THRESHOLDS = (50000, 20000, 10000)


@dataclass
class TrendingTopic:
    text: str
    source: str
    engagement_score: int
    category: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def http_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": WIKIPEDIA_USER_AGENT, **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _ranked_scores(count: int, base: int, step: int) -> List[int]:
    return [max(0, base - i * step) for i in range(count)]


def _build_ranked_topics(
    items: List[Dict[str, Any]],
    source: str,
    base: int,
    step: int,
    category: str = "",
) -> List[TrendingTopic]:
    topics = []
    scores = _ranked_scores(len(items), base, step)
    for i, item in enumerate(items):
        title = (item.get("title") or "").strip()
        if not title:
            continue
        topics.append(
            TrendingTopic(text=title, source=source, engagement_score=scores[i], category=category)
        )
    return topics


def fetch_wikipedia_pageviews(
    limit: int = PAGEVIEWS_LIMIT,
    http_get: Callable[[str], Any] = http_get_json,
    now: Optional[datetime] = None,
) -> List[TrendingTopic]:
    now = now or datetime.now(timezone.utc)
    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
        f"en.wikipedia/all-access/{now.year}/{now.month:02d}/{now.day:02d}"
    )
    data = http_get(url)

    articles = []
    for item in data.get("items", []):
        articles.extend(item.get("articles", []))

    topics = []
    for article in articles[:limit]:
        title = (article.get("article") or "").strip().replace("_", " ")
        if not title or title == "Main Page":
            continue
        topics.append(
            TrendingTopic(
                text=title,
                source="wikipedia",
                engagement_score=int(article.get("views", 0)),
            )
        )
    return topics


def fetch_wikipedia_recent_changes(
    limit: int = RECENT_CHANGES_LIMIT,
    http_get: Callable[[str], Any] = http_get_json,
) -> List[TrendingTopic]:
    url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=recentchanges"
        f"&rclimit={limit}&rcnamespace=0&rctype=new|edit&format=json"
    )
    data = http_get(url)
    entries = data.get("query", {}).get("recentchanges", [])
    return _build_ranked_topics(entries, "wikipedia", 50000, 1000)


def fetch_newsapi(
    api_key: str,
    query: str = NEWSAPI_QUERY,
    limit: int = NEWSAPI_LIMIT,
    http_get: Callable[[str], Any] = http_get_json,
) -> List[TrendingTopic]:
    if not api_key:
        return []
    url = (
        "https://newsapi.org/v2/everything?q="
        + urllib.parse.quote(query)
        + f"&pageSize={limit}&apiKey={api_key}"
    )
    data = http_get(url)
    articles = data.get("articles", [])
    return _build_ranked_topics(articles[:limit], "newsapi", 45000, 500, category=query)


def fetch_gdelt(
    query: str = GDELT_QUERY,
    limit: int = GDELT_LIMIT,
    http_get: Callable[[str], Any] = http_get_json,
) -> List[TrendingTopic]:
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?query="
        + urllib.parse.quote(query)
        + f"&mode=artlist&format=json&maxrecords={limit}"
    )
    data = http_get(url)

    if isinstance(data, dict):
        articles = data.get("articles") or data.get("results") or []
    else:
        articles = data or []
    return _build_ranked_topics(articles[:limit], "gdelt", 45000, 500, category=query)


def dedupe_topics(topics: List[TrendingTopic]) -> List[TrendingTopic]:
    best: Dict[str, TrendingTopic] = {}
    for topic in topics:
        key = topic.text.strip().lower()
        if key not in best or topic.engagement_score > best[key].engagement_score:
            best[key] = topic
    return list(best.values())


def select_by_threshold(
    topics: List[TrendingTopic],
    min_target: int = 3,
    max_target: int = 10,
    thresholds: Tuple[int, int, int] = DEFAULT_THRESHOLDS,
) -> List[TrendingTopic]:
    if not topics:
        return []

    working: List[TrendingTopic] = []
    chosen_threshold = None
    for threshold in sorted(thresholds, reverse=True):
        selected = [t for t in topics if t.engagement_score >= threshold]
        if len(selected) >= min_target:
            working = selected
            chosen_threshold = threshold
            break

    if chosen_threshold is None:
        lowest = sorted(thresholds)[0]
        working = [t for t in topics if t.engagement_score >= lowest]

    if not working:
        return []

    threshold = chosen_threshold if chosen_threshold is not None else sorted(thresholds)[0]
    while len(working) > max_target:
        threshold = int(threshold * 1.5)
        candidate = [t for t in topics if t.engagement_score >= threshold]
        if len(candidate) < min_target:
            break
        working = candidate
    return working


def build_default_fetchers(
    newsapi_key: str = "",
    pageviews_limit: int = PAGEVIEWS_LIMIT,
    recent_changes_limit: int = RECENT_CHANGES_LIMIT,
    newsapi_query: str = NEWSAPI_QUERY,
    newsapi_limit: int = NEWSAPI_LIMIT,
    gdelt_query: str = GDELT_QUERY,
    gdelt_limit: int = GDELT_LIMIT,
    http_get: Callable[[str], Any] = http_get_json,
) -> List[Tuple[str, Callable[[], List[TrendingTopic]]]]:
    fetchers: List[Tuple[str, Callable[[], List[TrendingTopic]]]] = [
        ("wikipedia", lambda: fetch_wikipedia_pageviews(limit=pageviews_limit, http_get=http_get)),
        (
            "wikipedia-changes",
            lambda: fetch_wikipedia_recent_changes(limit=recent_changes_limit, http_get=http_get),
        ),
        ("gdelt", lambda: fetch_gdelt(query=gdelt_query, limit=gdelt_limit, http_get=http_get)),
    ]
    if newsapi_key:
        fetchers.append(
            (
                "newsapi",
                lambda: fetch_newsapi(
                    api_key=newsapi_key,
                    query=newsapi_query,
                    limit=newsapi_limit,
                    http_get=http_get,
                ),
            )
        )
    return fetchers


class TrendingSelector:
    def __init__(
        self,
        fetchers: Optional[List[Tuple[str, Callable[[], List[TrendingTopic]]]]] = None,
        min_target: int = 3,
        max_target: int = 10,
        thresholds: Tuple[int, int, int] = DEFAULT_THRESHOLDS,
    ):
        self.fetchers = fetchers if fetchers is not None else build_default_fetchers()
        self.min_target = min_target
        self.max_target = max_target
        self.thresholds = thresholds

    @classmethod
    def from_config(cls, config, http_get: Callable[[str], Any] = http_get_json) -> "TrendingSelector":
        trending = config.get("trending", default={}) or {}
        thresholds = tuple(
            trending.get(key, default)
            for key, default in (
                ("wikipedia_threshold_high", 50000),
                ("wikipedia_threshold_medium", 20000),
                ("wikipedia_threshold_low", 10000),
            )
        )
        min_target = trending.get("min_topics_target", 3)
        max_target = trending.get("max_topics_target", 10)
        fetchers = build_default_fetchers(
            newsapi_key=config.get("api_keys", "newsapi_api_key", default="") or "",
            pageviews_limit=trending.get("pageviews_limit", PAGEVIEWS_LIMIT),
            recent_changes_limit=trending.get("recent_changes_limit", RECENT_CHANGES_LIMIT),
            newsapi_query=trending.get("newsapi_query", NEWSAPI_QUERY),
            newsapi_limit=trending.get("newsapi_limit", NEWSAPI_LIMIT),
            gdelt_query=trending.get("gdelt_query", GDELT_QUERY),
            gdelt_limit=trending.get("gdelt_limit", GDELT_LIMIT),
            http_get=http_get,
        )
        return cls(fetchers=fetchers, min_target=min_target, max_target=max_target, thresholds=thresholds)

    def fetch(self) -> List[TrendingTopic]:
        collected: List[TrendingTopic] = []
        for _name, func in self.fetchers:
            try:
                collected.extend(func())
            except Exception:
                continue
        if not collected:
            return []
        deduped = dedupe_topics(collected)
        return select_by_threshold(deduped, self.min_target, self.max_target, self.thresholds)
