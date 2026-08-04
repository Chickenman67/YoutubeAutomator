import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from script_generation.schema import Scene, Script


def test_scene_to_dict():
    scene = Scene(
        scene_id=1,
        narration="This is a test narration.",
        key_visual_keywords=["stick figure", "globe"],
        facts=["Fact 1", "Fact 2"]
    )
    
    d = scene.to_dict()
    assert d['scene_id'] == 1
    assert d['narration'] == "This is a test narration."
    assert d['key_visual_keywords'] == ["stick figure", "globe"]
    assert d['facts'] == ["Fact 1", "Fact 2"]


def test_scene_from_dict():
    data = {
        "scene_id": 2,
        "narration": "Test",
        "key_visual_keywords": ["sun"],
        "facts": ["Earth orbits the sun"]
    }
    
    scene = Scene.from_dict(data)
    assert scene.scene_id == 2
    assert scene.narration == "Test"


def test_script_to_json():
    script = Script(
        topic="Space",
        scenes=[
            Scene(1, "Narration 1", ["star"], ["Fact 1"]),
            Scene(2, "Narration 2", ["planet"], ["Fact 2"])
        ]
    )
    
    json_str = script.to_json()
    assert '"topic": "Space"' in json_str
    assert '"scene_id": 1' in json_str


def test_script_from_json():
    json_str = '''
    {
        "topic": "History",
        "scenes": [
            {
                "scene_id": 1,
                "narration": "Long ago...",
                "key_visual_keywords": ["castle"],
                "facts": ["1066"]
            }
        ]
    }
    '''
    
    script = Script.from_json(json_str)
    assert script.topic == "History"
    assert len(script.scenes) == 1
    assert script.scenes[0].scene_id == 1


def test_script_validate_scene_count():
    script = Script(
        topic="Test",
        scenes=[Scene(i, "x" * 100, ["a"], ["b"]) for i in range(1, 4)]
    )
    
    errors = script.validate()
    assert any("5-7 scenes" in e for e in errors)


def test_script_validate_scene_ids():
    script = Script(
        topic="Test",
        scenes=[
            Scene(1, "x" * 100, ["a"], ["b"]),
            Scene(3, "x" * 100, ["a"], ["b"]),
            Scene(3, "x" * 100, ["a"], ["b"]),
            Scene(4, "x" * 100, ["a"], ["b"]),
            Scene(5, "x" * 100, ["a"], ["b"]),
            Scene(6, "x" * 100, ["a"], ["b"])
        ]
    )
    
    errors = script.validate()
    assert any("incorrect scene_id" in e for e in errors)


def test_script_validate_narration_length():
    script = Script(
        topic="Test",
        scenes=[Scene(i, "short", ["a"], ["b"]) for i in range(1, 7)]
    )
    
    errors = script.validate()
    assert any("too short" in e for e in errors)


def test_script_validate_missing_keywords():
    script = Script(
        topic="Test",
        scenes=[Scene(i, "x" * 100, [], ["b"]) for i in range(1, 7)]
    )
    
    errors = script.validate()
    assert any("missing key_visual_keywords" in e for e in errors)


def test_script_validate_missing_facts():
    script = Script(
        topic="Test",
        scenes=[Scene(i, "x" * 100, ["a"], []) for i in range(1, 7)]
    )
    
    errors = script.validate()
    assert any("missing facts" in e for e in errors)


def test_script_validate_valid():
    script = Script(
        topic="Valid Topic",
        scenes=[Scene(i, "x" * 100, ["visual"], ["fact"]) for i in range(1, 7)]
    )
    
    errors = script.validate()
    assert len(errors) == 0
