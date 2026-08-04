import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
import urllib.error
from fact_check.fact_checker import (
    Confidence,
    FactChecker,
    FactCheckReport,
    FactCheckResult,
    SearchResult,
    build_source_url,
    search_wikipedia,
)
from script_generation.schema import Scene, Script


def make_narration(word_count=250):
    return " ".join(["word"] * word_count)


def make_scene(scene_id, facts):
    return Scene(
        scene_id=scene_id,
        narration=make_narration(),
        key_visual_keywords=["stick figure walking", "globe rotating", "clock ticking"],
        facts=facts,
    )


def make_script():
    return Script(
        topic="Roman Empire",
        scenes=[
            make_scene(1, ["The Roman Empire fell in 476 CE", "Rome was the capital"]),
            make_scene(2, ["The Colosseum was built in Rome"]),
        ],
    )


def fake_search(results):
    def _search(query, limit=3):
        return results
    return _search


def test_build_source_url_replaces_spaces():
    assert build_source_url("Fall of the Roman Empire") == (
        "https://en.wikipedia.org/wiki/Fall_of_the_Roman_Empire"
    )


def test_result_flagged_true_when_low():
    result = FactCheckResult(claim="nonsense", confidence=Confidence.LOW)
    assert result.flagged is True


def test_result_flagged_false_when_high():
    result = FactCheckResult(claim="real", confidence=Confidence.HIGH)
    assert result.flagged is False


def test_high_when_title_is_subject_of_claim():
    checker = FactChecker(search_func=fake_search([SearchResult(title="Earth", snippet="...", pageid=1)]))
    result = checker.check_claim("Earth is the third planet from the Sun")
    assert result.confidence == Confidence.HIGH
    assert result.matched_title == "Earth"
    assert result.source_url == "https://en.wikipedia.org/wiki/Earth"


def test_partial_match_is_medium_not_high():
    result = SearchResult(title="Fall of the Western Roman Empire", snippet="...", pageid=1)
    checker = FactChecker(search_func=fake_search([result]))
    check = checker.check_claim("The Roman Empire fell in 476 CE")
    assert check.confidence == Confidence.MEDIUM


def test_medium_when_partial_overlap():
    checker = FactChecker(search_func=fake_search([SearchResult(title="Colosseum of Rome", snippet="...", pageid=9)]))
    result = checker.check_claim("Ancient gladiators fought in Rome")
    assert result.confidence == Confidence.MEDIUM


def test_low_when_no_results():
    checker = FactChecker(search_func=fake_search([]))
    result = checker.check_claim("Unverifiable claim about a nonexistent topic")
    assert result.confidence == Confidence.LOW
    assert result.source_url is None


def test_low_when_no_token_overlap():
    checker = FactChecker(search_func=fake_search([SearchResult(title="Unrelated Topic", snippet="...", pageid=3)]))
    result = checker.check_claim("A completely different subject")
    assert result.confidence == Confidence.LOW


def test_check_script_enumerates_scene_facts():
    checker = FactChecker(search_func=fake_search([SearchResult(title="Roman Empire", snippet="...", pageid=5)]))
    report = checker.check_script(make_script())
    assert len(report.results) == 3
    assert [r.scene_id for r in report.results] == [1, 1, 2]
    assert [r.claim for r in report.results] == [
        "The Roman Empire fell in 476 CE",
        "Rome was the capital",
        "The Colosseum was built in Rome",
    ]


def test_report_flags_low_confidence_in_json():
    def mixed_search(query, limit=3):
        if "nonexistent" in query:
            return []
        return [SearchResult(title="Something Real", snippet="...", pageid=7)]
    checker = FactChecker(search_func=mixed_search)
    report = checker.check_script(make_script())
    assert report.low_confidence
    payload = json.loads(report.to_json())
    assert "low_confidence" in payload
    assert all(item["confidence"] == "low" for item in payload["low_confidence"])


def test_report_to_dict_round_trip():
    checker = FactChecker(search_func=fake_search([SearchResult(title="Earth", snippet="...", pageid=1)]))
    report = checker.check_script(make_script())
    d = report.to_dict()
    assert d["topic"] == "Roman Empire"
    assert len(d["results"]) == 3


def test_search_wikipedia_returns_empty_on_network_error(monkeypatch):
    class Boom:
        def Request(self, url, headers=None):
            return url

        def urlopen(self, req, timeout=None):
            raise urllib.error.URLError("network down")

    monkeypatch.setattr("fact_check.fact_checker.urllib.request", Boom())

    assert search_wikipedia("Earth") == []

    checker = FactChecker()
    result = checker.check_claim("Any claim")
    assert result.confidence == Confidence.LOW


def test_search_wikipedia_parses_response(monkeypatch):
    canned = {
        "query": {
            "search": [
                {"title": "Earth", "snippet": "third planet", "pageid": 1234},
                {"title": "Earth science", "snippet": "study", "pageid": 5678},
            ]
        }
    }

    class FakeResponse:
        def read(self):
            return json.dumps(canned).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakeRequestModule:
        def Request(self, url, headers=None):
            return url

        def urlopen(self, req, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("fact_check.fact_checker.urllib.request", FakeRequestModule())

    results = search_wikipedia("Earth")
    assert len(results) == 2
    assert results[0].title == "Earth"
    assert results[0].pageid == 1234
    assert results[0].snippet == "third planet"


def test_search_wikipedia_sends_query_and_user_agent(monkeypatch):
    captured = {}

    class FakeResp:
        def read(self):
            return json.dumps({"query": {"search": []}}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakeRequestModule:
        def Request(self, url, headers=None):
            captured["url"] = url
            captured["headers"] = headers
            return "req"

        def urlopen(self, req, timeout=None):
            return FakeResp()

    monkeypatch.setattr("fact_check.fact_checker.urllib.request", FakeRequestModule())

    search_wikipedia("The Roman Empire")
    assert "action=query" in captured["url"]
    assert "srsearch=The+Roman+Empire" in captured["url"]
    assert captured["headers"]["User-Agent"]
