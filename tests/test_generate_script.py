import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import MagicMock
from llm import GroqClient
from script_generation.generator import ScriptGenerator
from script_generation.schema import Script


def test_generate_script_returns_script_object():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    
    mock_response = {
        "topic": "Ancient Rome",
        "scenes": [
            {
                "scene_id": i,
                "narration": "This is narration for scene " + str(i) + ". " * 30,
                "key_visual_keywords": ["stick figure walking", "Roman column"],
                "facts": ["Rome was founded in 753 BCE", "Julius Caesar was assassinated in 44 BCE"]
            }
            for i in range(1, 7)
        ]
    }
    
    generator.client.generate_json = MagicMock(return_value=mock_response)
    
    result = generator.generate_script("Ancient Rome")
    
    assert isinstance(result, Script)
    assert result.topic == "Ancient Rome"
    assert len(result.scenes) == 6
    assert result.scenes[0].scene_id == 1
    assert len(result.scenes[0].key_visual_keywords) > 0
    assert len(result.scenes[0].facts) > 0


def test_generate_script_passes_system_prompt():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    
    mock_response = {
        "topic": "Test",
        "scenes": [{"scene_id": i, "narration": "x" * 100, "key_visual_keywords": ["a"], "facts": ["b"]} for i in range(1, 7)]
    }
    
    generator.client.generate_json = MagicMock(return_value=mock_response)
    
    generator.generate_script("Test Topic")
    
    call_kwargs = generator.client.generate_json.call_args
    assert call_kwargs.kwargs['system_prompt'] == generator.system_prompt


def test_generate_script_requests_json_structure():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    
    mock_response = {
        "topic": "Test",
        "scenes": [{"scene_id": 1, "narration": "x" * 100, "key_visual_keywords": ["a"], "facts": ["b"]}]
    }
    
    generator.client.generate_json = MagicMock(return_value=mock_response)
    
    generator.generate_script("Test", scene_count=5)
    
    call_kwargs = generator.client.generate_json.call_args
    prompt = call_kwargs.kwargs['prompt']
    
    assert "scene_id" in prompt
    assert "narration" in prompt
    assert "key_visual_keywords" in prompt
    assert "facts" in prompt
