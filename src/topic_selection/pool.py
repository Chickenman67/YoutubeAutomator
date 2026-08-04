import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

SECONDS_PER_DAY = 86400


@dataclass
class Topic:
    id: int
    text: str
    category: str = ""
    last_used: Optional[str] = None
    times_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Topic':
        return cls(
            id=int(data["id"]),
            text=str(data["text"]),
            category=str(data.get("category", "")),
            last_used=data.get("last_used"),
            times_used=int(data.get("times_used", 0)),
        )


class EvergreenPool:
    def __init__(self, path: str, rotation_days: int = 90, now: Optional[datetime] = None):
        self.path = Path(path)
        self.rotation_days = rotation_days
        self.now = now or datetime.now()
        self.topics = self._load()

    def _load(self) -> List[Topic]:
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

        entries = data.get("topics") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            return []

        topics = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            try:
                topics.append(Topic.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
        return topics

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"topics": [t.to_dict() for t in self.topics]}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def all_topics(self) -> List[Topic]:
        return list(self.topics)

    def _is_available(self, topic: Topic) -> bool:
        if topic.last_used is None:
            return True
        try:
            last = datetime.fromisoformat(topic.last_used)
        except (ValueError, TypeError):
            return True
        return (self.now - last).total_seconds() >= self.rotation_days * SECONDS_PER_DAY

    def available_topics(self) -> List[Topic]:
        return [t for t in self.topics if self._is_available(t)]

    def select_next(self) -> Optional[Topic]:
        available = self.available_topics()
        if not available:
            return None
        available.sort(key=lambda t: (t.last_used is not None, t.last_used or ""))
        chosen = available[0]
        chosen.last_used = self.now.isoformat()
        chosen.times_used += 1
        self.save()
        return chosen
