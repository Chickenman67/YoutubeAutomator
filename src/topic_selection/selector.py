import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from llm import GroqClient
from .explainability import ExplainabilityFilter
from .pool import EvergreenPool, Topic
from .trending import (TrendingSelector, TrendingTopic, http_get_json)

EVERGREEN_SOURCE = "evergreen"
EVERGREEN_REASON = "Pre-approved curated evergreen pool topic"
WEEKLY_TOTAL = 7


@dataclass
class ApprovedTopic:
    topic: str
    source: str
    category: str
    engagement_score: int
    explainability_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class TopicSelector:
    def __init__(
        self,
        trending_selector: TrendingSelector,
        explainability_filter: ExplainabilityFilter,
        evergreen_pool: EvergreenPool,
        trending_target: int = 5,
        evergreen_target: int = 2,
    ):
        self.trending_selector = trending_selector
        self.explainability_filter = explainability_filter
        self.evergreen_pool = evergreen_pool
        self.trending_target = trending_target
        self.evergreen_target = evergreen_target

    @classmethod
    def from_config(cls, config, http_get=http_get_json, now: Optional[datetime] = None) -> "TopicSelector":
        split = config.get("topic_split", default={}) or {}
        trending_pct = split.get("trending_percentage", 0.7)
        rotation_days = split.get("evergreen_rotation_days", 90)
        evergreen_path = config.get("paths", "evergreen_topics", default="topics/evergreen.json")

        total = WEEKLY_TOTAL
        trending_target = round(total * trending_pct)
        evergreen_target = total - trending_target

        trend_selector = TrendingSelector.from_config(config, http_get=http_get)
        api_key = config.get("api_keys", "groq_api_key", default="") or ""
        explainability = ExplainabilityFilter(
            GroqClient(api_key=api_key) if api_key else None
        )
        pool = EvergreenPool(path=evergreen_path, rotation_days=rotation_days, now=now)

        return cls(
            trending_selector=trend_selector,
            explainability_filter=explainability,
            evergreen_pool=pool,
            trending_target=trending_target,
            evergreen_target=evergreen_target,
        )

    def _from_trending(self, topic: TrendingTopic, reason: str) -> ApprovedTopic:
        return ApprovedTopic(
            topic=topic.text,
            source=topic.source,
            category=topic.category,
            engagement_score=topic.engagement_score,
            explainability_reason=reason,
        )

    def _from_evergreen(self, topic: Topic) -> ApprovedTopic:
        return ApprovedTopic(
            topic=topic.text,
            source=EVERGREEN_SOURCE,
            category=topic.category,
            engagement_score=0,
            explainability_reason=EVERGREEN_REASON,
        )

    def select(self) -> List[ApprovedTopic]:
        trending = self.trending_selector.fetch()
        approved_pairs = self.explainability_filter.filter_topics(trending)
        approved_trending = [
            self._from_trending(topic, reason)
            for topic, reason in approved_pairs[: self.trending_target]
        ]

        total = self.trending_target + self.evergreen_target
        evergreen_needed = max(self.evergreen_target, total - len(approved_trending))

        approved_evergreen = []
        for _ in range(evergreen_needed):
            chosen = self.evergreen_pool.select_next()
            if chosen is None:
                break
            approved_evergreen.append(self._from_evergreen(chosen))

        return approved_trending + approved_evergreen
