import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm import GroqClient, load_video_script_prompt


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
