import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Callable, Dict, Any, List, Optional

from script_generation.schema import Script


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


STOPWORDS = {
    "a", "about", "an", "and", "are", "as", "at", "by", "for", "from", "has",
    "had", "have", "in", "is", "it", "its", "not", "of", "on", "the", "that",
    "this", "to", "was", "were", "with", "it's",
    "ad", "bc", "bce", "ce", "st", "nd", "rd", "th",
}

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_USER_AGENT = "YoutubeAutomator/0.1"


@dataclass
class SearchResult:
    title: str
    snippet: str
    pageid: int


@dataclass
class FactCheckResult:
    claim: str
    confidence: Confidence
    scene_id: Optional[int] = None
    matched_title: Optional[str] = None
    source_url: Optional[str] = None
    reason: Optional[str] = None

    @property
    def flagged(self) -> bool:
        return self.confidence == Confidence.LOW

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["confidence"] = self.confidence.value
        d["flagged"] = self.flagged
        return d


@dataclass
class FactCheckReport:
    topic: str
    results: List[FactCheckResult]

    @property
    def low_confidence(self) -> List[FactCheckResult]:
        return [r for r in self.results if r.flagged]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "results": [r.to_dict() for r in self.results],
            "low_confidence": [r.to_dict() for r in self.low_confidence],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def build_source_url(title: str) -> str:
    return f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-zA-Z]+", text.lower())) - STOPWORDS


def search_wikipedia(query: str, limit: int = 5) -> List[SearchResult]:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": str(limit),
        "format": "json",
        "utf8": "1",
    }
    url = f"{WIKIPEDIA_API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": WIKIPEDIA_USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError):
        return []

    results = []
    for item in data.get("query", {}).get("search", []):
        results.append(
            SearchResult(
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                pageid=int(item.get("pageid", 0)),
            )
        )
    return results


def _evaluate(claim: str, results: List[SearchResult]):
    """Return (confidence, matched result, reason) for a claim vs search results."""
    claim_tokens = _tokens(claim)
    if not results or not claim_tokens:
        return Confidence.LOW, None, "no verifiable Wikipedia match found"

    best = None
    best_overlap = 0
    best_contained = False

    for result in results:
        title_tokens = _tokens(result.title)
        if not title_tokens:
            continue
        overlap = len(claim_tokens & title_tokens)
        contained = title_tokens <= claim_tokens
        if (overlap > best_overlap) or (overlap == best_overlap and contained):
            best = result
            best_overlap = overlap
            best_contained = contained

    if best is None or best_overlap == 0:
        reason = (
            "no matching article found; claim may be unverifiable or conflict with sources"
            if best
            else "no verifiable Wikipedia match found"
        )
        return Confidence.LOW, best, reason
    if best_contained:
        return Confidence.HIGH, best, "exact Wikipedia article match"
    return Confidence.MEDIUM, best, "partial match with Wikipedia article"


class FactChecker:
    def __init__(self, search_func: Callable[[str], List[SearchResult]] = search_wikipedia):
        self.search_func = search_func

    def check_claim(self, claim: str) -> FactCheckResult:
        results = self.search_func(claim)
        confidence, matched, reason = _evaluate(claim, results)
        source_url = build_source_url(matched.title) if matched else None
        return FactCheckResult(
            claim=claim,
            confidence=confidence,
            matched_title=matched.title if matched else None,
            source_url=source_url,
            reason=reason,
        )

    def check_script(self, script: Script) -> FactCheckReport:
        results: List[FactCheckResult] = []
        for scene in script.scenes:
            for claim in scene.facts:
                result = self.check_claim(claim)
                result.scene_id = scene.scene_id
                results.append(result)
        return FactCheckReport(topic=script.topic, results=results)
