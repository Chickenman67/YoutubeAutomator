import json
import logging
from datetime import date
from pathlib import Path


def daily_key(day=None) -> str:
    return (day or date.today()).isoformat()


class QuotaExceededError(Exception):
    pass


class QuotaTracker:
    def __init__(self, quota_path: str = "config/quota.json", daily_limit: int = 10000):
        self.quota_path = Path(quota_path)
        self.daily_limit = daily_limit
        self.logger = logging.getLogger(__name__)
        self._usage = self._load()

    def _load(self) -> dict:
        if not self.quota_path.is_file():
            return {}
        try:
            data = json.loads(self.quota_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def used(self, day=None) -> int:
        return int(self._usage.get(daily_key(day), 0))

    def remaining(self, day=None) -> int:
        return max(0, self.daily_limit - self.used(day))

    def record(self, cost: int, day=None) -> int:
        key = daily_key(day)
        new_total = self.used(day) + cost
        if new_total > self.daily_limit:
            raise QuotaExceededError(
                f"daily quota exceeded: {new_total} > {self.daily_limit}"
            )
        self._usage[key] = new_total
        self._save()
        self.logger.info("quota used today: %s", new_total)
        return new_total

    def _save(self):
        self.quota_path.parent.mkdir(parents=True, exist_ok=True)
        self.quota_path.write_text(json.dumps(self._usage, indent=2), encoding="utf-8")
