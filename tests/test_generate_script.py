import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import MagicMock
from llm import GroqClient
from script_generation.generator import ScriptGenerator
from script_generation.schema import Script


def make_valid_mock_response(topic="Test Topic", scene_count=6):
    return {
        "topic": topic,
        "scenes": [
            {
                "scene_id": i,
                "narration": "word " * 250,
                "key_visual_keywords": ["stick figure walking", "globe rotating", "clock ticking"],
                "facts": ["Fact one", "Fact two", "Fact three"]
            }
            for i in range(1, scene_count + 1)
        ]
    }


def test_generate_script_returns_script_object():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    
    mock_response = make_valid_mock_response(topic="Ancient Rome")
    
    generator.client.generate_json = MagicMock(return_value=mock_response)
    
    result = generator.generate_script("Ancient Rome")
    
    assert isinstance(result, Script)
    assert result.topic == "Ancient Rome"
    assert len(result.scenes) == 6
    assert result.scenes[0].scene_id == 1
    assert len(result.scenes[0].key_visual_keywords) == 3
    assert len(result.scenes[0].facts) == 3


def test_generate_script_passes_system_prompt():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    
    generator.client.generate_json = MagicMock(return_value=make_valid_mock_response())
    
    generator.generate_script("Test Topic")
    
    call_kwargs = generator.client.generate_json.call_args
    assert call_kwargs.kwargs['system_prompt'] == generator.system_prompt
    assert "narration" in generator.system_prompt.lower()


def test_generate_script_passes_humanized_prompt():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    generator.client.generate_json = MagicMock(return_value=make_valid_mock_response())
    
    generator.generate_script("Test Topic")
    
    prompt = generator.system_prompt.lower()
    assert "contraction" in prompt
    assert "conversational" in prompt
    assert "spoken" in prompt or "narration" in prompt


def test_generate_script_requests_json_structure():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    
    generator.client.generate_json = MagicMock(return_value=make_valid_mock_response())
    
    generator.generate_script("Test", scene_count=5)
    
    call_kwargs = generator.client.generate_json.call_args
    prompt = call_kwargs.kwargs['prompt']
    
    assert "scene_id" in prompt
    assert "narration" in prompt
    assert "key_visual_keywords" in prompt
    assert "facts" in prompt


def test_generate_script_raises_on_invalid_scenes():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    
    invalid_response = {
        "topic": "Bad",
        "scenes": [
            {"scene_id": i, "narration": "too short", "key_visual_keywords": [], "facts": []}
            for i in range(1, 4)
        ]
    }
    
    generator.client.generate_json = MagicMock(return_value=invalid_response)
    
    with pytest.raises(ValueError, match="failed validation"):
        generator.generate_script("Bad Topic")
