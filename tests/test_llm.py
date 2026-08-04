import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from llm import GroqClient, load_video_script_prompt


def test_load_video_script_prompt_exists():
    prompt = load_video_script_prompt()
    assert len(prompt) > 100
    assert "narration" in prompt.lower() or "spoken" in prompt.lower() or "conversational" in prompt.lower()


def test_load_video_script_prompt_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_video_script_prompt(str(tmp_path / "missing.txt"))


def test_load_prompt_keeps_contractions_guidance():
    prompt = load_video_script_prompt()
    assert "contraction" in prompt.lower()


def test_load_prompt_avoids_visual_punctuation_rule():
    prompt = load_video_script_prompt()
    assert "em dash" in prompt.lower() or "semicolon" in prompt.lower()


def test_groq_client_missing_key_raises():
    import os
    if os.getenv('GROQ_API_KEY'):
        pytest.skip("GROQ_API_KEY is set, cannot test missing key")
    with pytest.raises(ValueError):
        GroqClient(api_key=None)


def test_groq_client_uses_model():
    import os
    key = os.getenv('GROQ_API_KEY', 'test-key')
    client = GroqClient(api_key=key, model="test-model")
    assert client.model == "test-model"
    assert client.api_key == key


def test_generate_builds_messages():
    from unittest.mock import MagicMock
    client = GroqClient(api_key="test-key")
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Generated content"
    client.client.chat.completions.create = MagicMock(return_value=mock_response)
    
    result = client.generate("Write a script", system_prompt="You are a narrator")
    
    assert result == "Generated content"
    call_kwargs = client.client.chat.completions.create.call_args
    assert call_kwargs.kwargs['model'] == "llama-3.1-70b-versatile"
    assert len(call_kwargs.kwargs['messages']) == 2
    assert call_kwargs.kwargs['messages'][0] == {"role": "system", "content": "You are a narrator"}
    assert call_kwargs.kwargs['messages'][1] == {"role": "user", "content": "Write a script"}


def test_generate_json_parses(monkeypatch):
    import json
    from unittest.mock import MagicMock
    
    client = GroqClient(api_key="test-key")
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({"topic": "test", "scenes": []})
    client.client.chat.completions.create = MagicMock(return_value=mock_response)
    
    result = client.generate_json("Return JSON")
    
    assert result == {"topic": "test", "scenes": []}


def test_generate_json_sets_response_format(monkeypatch):
    from unittest.mock import MagicMock
    
    client = GroqClient(api_key="test-key")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "{}"
    client.client.chat.completions.create = MagicMock(return_value=mock_response)
    
    client.generate_json("Return JSON")
    
    call_kwargs = client.client.chat.completions.create.call_args
    assert call_kwargs.kwargs['response_format'] == {"type": "json_object"}
