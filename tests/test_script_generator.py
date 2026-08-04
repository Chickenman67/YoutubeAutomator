import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import MagicMock, patch
from llm import GroqClient
from script_generation.generator import ScriptGenerator


def test_script_generator_loads_prompt():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    assert len(generator.system_prompt) > 100
    assert "narration" in generator.system_prompt.lower()


def test_generate_text_calls_client_with_prompt():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    
    generator.client.generate = MagicMock(return_value="This is generated narration")
    
    result = generator.generate_text("The Roman Empire", "Include 3 facts")
    
    assert result == "This is generated narration"
    call_kwargs = generator.client.generate.call_args
        
    assert "The Roman Empire" in call_kwargs.kwargs['prompt']
    assert generator.system_prompt == call_kwargs.kwargs['system_prompt']
    assert call_kwargs.kwargs['temperature'] == 0.8


def test_generate_text_uses_loaded_prompt():
    client = GroqClient(api_key="test-key")
    generator = ScriptGenerator(client)
    generator.client.generate = MagicMock(return_value="x")
    generator.generate_text("Space")
    
    call_kwargs = generator.client.generate.call_args
    assert call_kwargs.kwargs['system_prompt'] == generator.system_prompt
    assert "Space" in call_kwargs.kwargs['prompt']
