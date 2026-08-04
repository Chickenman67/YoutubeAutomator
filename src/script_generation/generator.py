import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm import GroqClient, load_video_script_prompt
from .schema import Script, Scene


class ScriptGenerator:
    def __init__(self, groq_client: GroqClient, prompt_path: str = "config/video_script_prompt.txt"):
        self.client = groq_client
        self.system_prompt = load_video_script_prompt(prompt_path)
    
    def generate_text(self, topic: str, instructions: str = "") -> str:
        prompt = f"Generate narration for an educational video about: {topic}"
        if instructions:
            prompt += f"\n\n{instructions}"
        
        return self.client.generate(
            prompt=prompt,
            system_prompt=self.system_prompt,
            temperature=0.8
        )
    
    def generate_script(self, topic: str, scene_count: int = 6) -> Script:
        prompt = f"""Generate a {scene_count}-scene video script about: {topic}

Return a JSON object with this structure:
{{
  "topic": "{topic}",
  "scenes": [
    {{
      "scene_id": 1,
      "narration": "60-90 seconds of spoken narration following the system prompt style",
      "key_visual_keywords": ["stick figure running", "clock ticking", "map of Europe"],
      "facts": ["The Roman Empire fell in 476 CE", "Constantinople was the capital"]
    }}
  ]
}}

Each scene must have:
- scene_id: sequential integer starting at 1
- narration: 200-400 words (60-90 seconds when spoken)
- key_visual_keywords: 3-5 concrete, actionable visual descriptions for stick figure animations
- facts: 2-4 verifiable factual claims (dates, names, events, numbers)

Make narration engaging, conversational, and educational. Visual keywords should be simple actions or objects that work with stick figures and basic shapes."""
        
        response_dict = self.client.generate_json(
            prompt=prompt,
            system_prompt=self.system_prompt,
            temperature=0.8
        )
        
        script = Script.from_dict(response_dict)
        errors = script.validate()
        if errors:
            raise ValueError(f"Generated script failed validation: {'; '.join(errors)}")
        
        return script
