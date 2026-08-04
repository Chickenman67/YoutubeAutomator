import os
from pathlib import Path
from typing import Optional, Dict, Any
from groq import Groq


class GroqClient:
    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.1-70b-versatile"):
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError("Groq API key not provided. Set GROQ_API_KEY environment variable or pass api_key parameter.")
        
        self.model = model
        self.client = Groq(api_key=self.api_key)
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        return response.choices[0].message.content
    
    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[Any, Any]:
        import json
        
        response = self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            response_format={"type": "json_object"},
            **kwargs
        )
        
        return json.loads(response)


def load_video_script_prompt(prompt_path: str = "config/video_script_prompt.txt") -> str:
    path = Path(prompt_path)
    if not path.exists():
        raise FileNotFoundError(f"Video script prompt not found: {prompt_path}")
    
    return path.read_text(encoding='utf-8')
