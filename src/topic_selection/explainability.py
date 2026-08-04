from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from llm import GroqClient
from .trending import TrendingTopic


@dataclass
class ExplainabilityVerdict:
    approved: bool = False
    reason: str = ""


class ExplainabilityFilter:
    """LLM quick-check that a trending topic can be explained in an
    educational video with verifiable facts. Fails closed: any topic that
    cannot be confirmed (no client, bad response, LLM error) is rejected."""

    def __init__(
        self,
        groq_client: Optional[GroqClient] = None,
        temperature: float = 0.2,
    ):
        self.client = groq_client
        self.temperature = temperature

    def _build_prompt(self, topic: TrendingTopic) -> str:
        return f"""Topic: {topic.text}
Category: {topic.category or "unknown"}

Can this be explained in a 5-10 minute educational video with verifiable facts?

Answer with a JSON object:
{{
  "answer": "Yes" or "No",
  "reason": "one sentence explaining why"
}}

Rules:
- Answer "Yes" only if the topic can be clearly explained with accurate, verifiable facts in 5-10 minutes.
- Answer "No" if it is too broad, too narrow, speculative, or not well-suited to education."""

    def _parse(self, raw: Dict[str, Any]) -> ExplainabilityVerdict:
        data = raw or {}
        answer = str(data.get("answer") or "").strip().lower().strip(".,!? \t")
        reason = str(data.get("reason") or "").strip()
        return ExplainabilityVerdict(approved=answer == "yes", reason=reason)

    def evaluate(self, topic: TrendingTopic) -> ExplainabilityVerdict:
        if self.client is None:
            return ExplainabilityVerdict(
                False, "Explainability check unavailable (no LLM configured)"
            )
        try:
            raw = self.client.generate_json(
                prompt=self._build_prompt(topic), temperature=self.temperature
            )
        except Exception:
            return ExplainabilityVerdict(False, "Explainability check failed")
        return self._parse(raw)

    def filter_topics(self, topics: List[TrendingTopic]) -> List[Tuple[TrendingTopic, str]]:
        approved = []
        for topic in topics:
            verdict = self.evaluate(topic)
            if verdict.approved:
                approved.append((topic, verdict.reason))
        return approved
