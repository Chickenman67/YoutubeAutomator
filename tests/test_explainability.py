import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from unittest.mock import MagicMock
from llm import GroqClient
from topic_selection.explainability import ExplainabilityFilter, ExplainabilityVerdict
from topic_selection.trending import TrendingTopic


def make_topic(text="The Fall of the Roman Empire", category="history"):
    return TrendingTopic(text=text, source="wikipedia", engagement_score=80000, category=category)


def make_filter(raw):
    client = GroqClient(api_key="test-key")
    client.generate_json = MagicMock(return_value=raw)
    return client, ExplainabilityFilter(client)


def test_prompt_asks_educational_explainability_question():
    client, filt = make_filter({"answer": "Yes", "reason": "Clear facts exist."})
    filt.evaluate(make_topic())
    prompt = client.generate_json.call_args.kwargs['prompt']
    assert "Can this be explained in a 5-10 minute educational video" in prompt
    assert "Roman Empire" in prompt


def test_yes_answer_approved_with_reason():
    _, filt = make_filter({"answer": "Yes", "reason": "Plenty of verifiable facts."})
    verdict = filt.evaluate(make_topic())
    assert verdict.approved is True
    assert verdict.reason == "Plenty of verifiable facts."


def test_no_answer_rejected():
    _, filt = make_filter({"answer": "No", "reason": "Too broad to cover."})
    verdict = filt.evaluate(make_topic())
    assert verdict.approved is False
    assert verdict.reason == "Too broad to cover."


def test_lowercase_and_yes_with_punctuation_approved():
    _, filt = make_filter({"answer": "yes", "reason": "ok"})
    assert filt.evaluate(make_topic()).approved is True

    _, filt2 = make_filter({"answer": "YES", "reason": "ok"})
    assert filt2.evaluate(make_topic()).approved is True

    _, filt3 = make_filter({"answer": "Yes.", "reason": "ok"})
    assert filt3.evaluate(make_topic()).approved is True


def test_variant_answers_rejected():
    _, filt = make_filter({"answer": "yeah", "reason": "ok"})
    assert filt.evaluate(make_topic()).approved is False


def test_missing_answer_rejected():
    _, filt = make_filter({"reason": "no answer field"})
    assert filt.evaluate(make_topic()).approved is False


def test_llm_exception_degrades_to_reject():
    client = GroqClient(api_key="test-key")
    client.generate_json = MagicMock(side_effect=RuntimeError("groq down"))
    filt = ExplainabilityFilter(client)
    assert filt.evaluate(make_topic()).approved is False


def test_no_client_rejects_without_crash():
    filt = ExplainabilityFilter(groq_client=None)
    verdict = filt.evaluate(make_topic())
    assert verdict.approved is False
    assert verdict.reason


def test_filter_topics_keeps_only_approved_with_reason():
    client = GroqClient(api_key="test-key")

    def routed_llm(prompt, **kwargs):
        if "Black Holes" in prompt:
            return {"answer": "Yes", "reason": "Great subject."}
        return {"answer": "No", "reason": "Niche."}

    client.generate_json = MagicMock(side_effect=routed_llm)
    filt = ExplainabilityFilter(client)
    topics = [make_topic("Black Holes", "science"), make_topic("Obscure Thing", "history")]
    result = filt.filter_topics(topics)
    assert len(result) == 1
    topic, reason = result[0]
    assert topic.text == "Black Holes"
    assert reason == "Great subject."


def test_verdict_defaults():
    v = ExplainabilityVerdict()
    assert v.approved is False
    assert v.reason == ""
