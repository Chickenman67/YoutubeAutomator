import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from upload.quota import QuotaExceededError, QuotaTracker


def test_new_tracker_starts_at_zero(tmp_path):
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"))
    assert tracker.used() == 0
    assert tracker.remaining() == 10000


def test_record_adds_cost_and_persists(tmp_path):
    path = tmp_path / "quota.json"
    tracker = QuotaTracker(quota_path=str(path))
    assert tracker.record(1600) == 1600
    reloaded = QuotaTracker(quota_path=str(path))
    assert reloaded.used() == 1600
    assert reloaded.remaining() == 8400


def test_record_accumulates_costs(tmp_path):
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"))
    tracker.record(1600)
    tracker.record(1600)
    assert tracker.used() == 3200


def test_record_raises_when_exceeding_limit(tmp_path):
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"), daily_limit=2000)
    tracker.record(1600)
    with pytest.raises(QuotaExceededError):
        tracker.record(1600)


def test_usage_is_per_day(tmp_path):
    tracker = QuotaTracker(quota_path=str(tmp_path / "quota.json"))
    tracker.record(1600, day=date(2026, 8, 1))
    assert tracker.used(date(2026, 8, 1)) == 1600
    assert tracker.used(date(2026, 8, 2)) == 0
    assert tracker.remaining(date(2026, 8, 2)) == 10000


def test_missing_or_corrupt_file_counts_as_zero(tmp_path):
    path = tmp_path / "quota.json"
    path.write_text("{not json", encoding="utf-8")
    tracker = QuotaTracker(quota_path=str(path))
    assert tracker.used() == 0
