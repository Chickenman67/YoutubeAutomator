import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from script_generation.schema import Scene, Script


def make_valid_narration(word_count=250):
    words = ["word"] * word_count
    return " ".join(words)


def make_valid_scene(scene_id):
    return Scene(
        scene_id=scene_id,
        narration=make_valid_narration(),
        key_visual_keywords=["stick figure walking", "globe rotating", "clock ticking"],
        facts=["Rome was founded in 753 BCE", "Caesar ruled Rome", "The empire spanned three continents"]
    )


def make_valid_script(scene_count=6):
    return Script(
        topic="Valid Topic",
        scenes=[make_valid_scene(i) for i in range(1, scene_count + 1)]
    )


def test_scene_to_dict():
    scene = make_valid_scene(1)
    
    d = scene.to_dict()
    assert d['scene_id'] == 1
    assert d['key_visual_keywords'] == ["stick figure walking", "globe rotating", "clock ticking"]
    assert len(d['facts']) == 3


def test_scene_from_dict():
    data = {
        "scene_id": 2,
        "narration": make_valid_narration(),
        "key_visual_keywords": ["sun rising", "earth rotating", "moon orbiting"],
        "facts": ["Earth orbits the sun", "The moon orbits Earth"]
    }
    
    scene = Scene.from_dict(data)
    assert scene.scene_id == 2


def test_script_to_json():
    script = make_valid_script(scene_count=2)
    
    json_str = script.to_json()
    assert '"topic": "Valid Topic"' in json_str
    assert '"scene_id": 1' in json_str


def test_script_from_json():
    json_str = f'''
    {{
        "topic": "History",
        "scenes": [
            {{
                "scene_id": 1,
                "narration": "{make_valid_narration()}",
                "key_visual_keywords": ["castle walls", "soldiers marching", "banner raised"],
                "facts": ["The battle happened in 1066", "William the Conqueror led the invasion"]
            }}
        ]
    }}
    '''
    
    script = Script.from_json(json_str)
    assert script.topic == "History"
    assert len(script.scenes) == 1
    assert script.scenes[0].scene_id == 1


def test_script_validate_scene_count():
    script = make_valid_script(scene_count=3)
    
    errors = script.validate()
    assert any("5-7 scenes" in e for e in errors)


def test_script_validate_scene_ids():
    scenes = make_valid_script(scene_count=6).scenes
    scenes[1] = Scene(3, scenes[1].narration, scenes[1].key_visual_keywords, scenes[1].facts)
    script = Script(topic="Test", scenes=scenes)
    
    errors = script.validate()
    assert any("incorrect scene_id" in e for e in errors)


def test_script_validate_narration_word_count():
    too_short = make_valid_scene(1)
    too_short.narration = "too short"
    script = Script(topic="Test", scenes=[too_short] + [make_valid_scene(i) for i in range(2, 7)])
    
    errors = script.validate()
    assert any("200-400" in e for e in errors)


def test_script_validate_missing_keywords():
    scene = make_valid_scene(1)
    scene.key_visual_keywords = []
    script = Script(topic="Test", scenes=[scene] + [make_valid_scene(i) for i in range(2, 7)])
    
    errors = script.validate()
    assert any("missing key_visual_keywords" in e for e in errors)


def test_script_validate_keyword_count():
    scene = make_valid_scene(1)
    scene.key_visual_keywords = ["only one"]
    script = Script(topic="Test", scenes=[scene] + [make_valid_scene(i) for i in range(2, 7)])
    
    errors = script.validate()
    assert any("visual keywords, expected 3-5" in e for e in errors)


def test_script_validate_missing_facts():
    scene = make_valid_scene(1)
    scene.facts = []
    script = Script(topic="Test", scenes=[scene] + [make_valid_scene(i) for i in range(2, 7)])
    
    errors = script.validate()
    assert any("missing facts" in e for e in errors)


def test_script_validate_fact_count():
    scene = make_valid_scene(1)
    scene.facts = ["only one fact"]
    script = Script(topic="Test", scenes=[scene] + [make_valid_scene(i) for i in range(2, 7)])
    
    errors = script.validate()
    assert any("facts, expected 2-4" in e for e in errors)


def test_script_validate_valid():
    script = make_valid_script()
    
    errors = script.validate()
    assert len(errors) == 0
