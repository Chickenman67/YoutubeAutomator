import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import MagicMock
from llm import GroqClient
from metadata.generator import FOOTER, Metadata, MetadataGenerator
from script_generation.schema import Scene, Script


def make_scene(sid):
    return Scene(
        scene_id=sid,
        narration="The narrative content for this scene " * 6,
        key_visual_keywords=["a", "b", "c"],
        facts=["fact one", "fact two"],
    )


def make_script(scene_count=3):
    return Script(topic="Space", scenes=[make_scene(i) for i in range(1, scene_count + 1)])


def canned_raw(**over):
    data = {
        "title": "Space Exploration: The Ultimate Guide",
        "description": "A quick summary of the video. It covers the key ideas of space travel. And it ends with a conclusion.",
        "tags": ["space", "planets", "rockets"],
    }
    data.update(over)
    return data


def make_generator(raw):
    client = GroqClient(api_key="test-key")
    client.generate_json = MagicMock(return_value=raw)
    return client, MetadataGenerator(client)


def test_metadata_to_dict_to_json():
    meta = Metadata(title="T", description="D", tags=["a", "b"], category=27)
    d = meta.to_dict()
    assert d["title"] == "T"
    assert json.loads(meta.to_json())["category"] == 27


def test_generate_metadata_calls_llm_and_returns_object():
    client, gen = make_generator(canned_raw())
    meta = gen.generate_metadata(make_script())
    assert isinstance(meta, Metadata)
    assert client.generate_json.called
    assert meta.category == 27


def test_generator_prompt_contains_topic_and_scene_text():
    client, gen = make_generator(canned_raw())
    gen.generate_metadata(make_script())
    prompt = client.generate_json.call_args.kwargs['prompt']
    assert "Space" in prompt
    assert "The narrative content" in prompt


def test_title_truncated_to_max_length():
    client, gen = make_generator(canned_raw(title="T" * 100))
    gen.title_max_length = 10
    meta = gen.generate_metadata(make_script())
    assert len(meta.title) <= 10


def test_short_title_untouched():
    client, gen = make_generator(canned_raw(title="Space"))
    meta = gen.generate_metadata(make_script())
    assert meta.title == "Space"


def test_description_contains_summary_timestamps_and_footer():
    client, gen = make_generator(canned_raw())
    meta = gen.generate_metadata(make_script(scene_count=3))
    assert "covers the key ideas" in meta.description
    assert "0:00" in meta.description
    assert "1:10" in meta.description
    assert "2:20" in meta.description
    assert FOOTER in meta.description


def test_tags_deduped_trimmed_case_insensitive():
    raw = canned_raw(tags=["Space", " space ", "", "space", "rockets", "  "])
    client, gen = make_generator(raw)
    meta = gen.generate_metadata(make_script())
    assert meta.tags.count("space") == 1
    assert meta.tags.count("rockets") == 1
    assert all(t == t.strip().lower() for t in meta.tags)
    assert "" not in meta.tags
    assert len(meta.tags) == len(set(meta.tags))


def test_tags_padded_to_minimum_from_script():
    raw = canned_raw(tags=["space"])
    client, gen = make_generator(raw)
    gen.tag_count_min = 3
    gen.tag_count_max = 15
    meta = gen.generate_metadata(make_script())
    assert len(meta.tags) >= 3
    assert "a" in meta.tags
    assert "b" in meta.tags
    assert "space" in meta.tags


def test_tags_capped_at_max():
    raw = canned_raw(tags=[f"tag{i}" for i in range(30)])
    client, gen = make_generator(raw)
    gen.tag_count_max = 15
    meta = gen.generate_metadata(make_script())
    assert len(meta.tags) <= 15


def test_category_always_education():
    client, gen = make_generator(canned_raw())
    meta = gen.generate_metadata(make_script())
    assert meta.category == 27
