import json
import re
from dataclasses import asdict, dataclass
from typing import Dict, Any, List

from llm import GroqClient
from script_generation.schema import Script

FOOTER = (
    "If you enjoyed this video, please like and subscribe for more educational content!"
)
YOUTUBE_CATEGORY_EDUCATION = 27


@dataclass
class Metadata:
    title: str
    description: str
    tags: List[str]
    category: int = YOUTUBE_CATEGORY_EDUCATION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class MetadataGenerator:
    def __init__(
        self,
        groq_client: GroqClient,
        title_max_length: int = 60,
        tag_count_min: int = 10,
        tag_count_max: int = 15,
        category_id: int = YOUTUBE_CATEGORY_EDUCATION,
        scene_duration: int = 70,
    ):
        self.client = groq_client
        self.title_max_length = title_max_length
        self.tag_count_min = tag_count_min
        self.tag_count_max = tag_count_max
        self.category_id = category_id
        self.scene_duration = scene_duration

    def _build_prompt(self, script: Script) -> str:
        scene_lines = [
            f"Scene {scene.scene_id}: {scene.narration}" for scene in script.scenes
        ]
        scenes = "\n".join(scene_lines)

        return f"""Generate YouTube metadata for an educational video titled "{script.topic}".

Topic category: {script.topic}

Here are the scene narrations:
{scenes}

Return a JSON object with exactly these fields:
{{
  "title": "SEO-optimized title (under {self.title_max_length} chars, includes the main keyword, creates curiosity)",
  "description": "2-3 sentence summary of the video (no timestamps, no footer)",
  "tags": ["{self.tag_count_min}-{self.tag_count_max} relevant, lowercase, single tags"]
}}

Rules:
- Title must be {self.title_max_length} characters or fewer and include the main keyword "{script.topic}".
- Description must be a 2-3 sentence engaging summary only.
- Tags must be {self.tag_count_min}-{self.tag_count_max}, relevant to the topic and its category."""

    def _format_timestamp(self, seconds: int) -> str:
        m, s = divmod(seconds, 60)
        return f"{m}:{s:02d}"

    def _chapter_label(self, scene) -> str:
        words = scene.narration.split()
        label = " ".join(words[:10])
        if len(words) > 10:
            label += "..."
        return label

    def _build_description(self, raw: Dict[str, Any], script: Script) -> str:
        summary = (raw.get("description") or "").strip()
        lines = []
        if summary:
            lines.append(summary)
        start = 0
        for scene in script.scenes:
            lines.append(f"{self._format_timestamp(start)} - {self._chapter_label(scene)}")
            start += self.scene_duration
        lines.append(FOOTER)
        return "\n\n".join(lines)

    def _normalize_title(self, title: str) -> str:
        title = title.strip()
        if len(title) > self.title_max_length:
            title = title[: self.title_max_length].rsplit(" ", 1)[0]
        return title

    def _derive_tags(self, script: Script) -> List[str]:
        candidates = []
        topic = script.topic.strip()
        if topic:
            candidates.append(topic)
            candidates.extend(re.split(r"[^a-z0-9]+", topic.lower()))
        for scene in script.scenes:
            candidates.extend(scene.key_visual_keywords)
        return candidates

    def _normalize_tags(self, tags: List[str], script: Script) -> List[str]:
        result = []
        seen = set()
        for tag in tags:
            cleaned = tag.strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)

        for candidate in self._derive_tags(script):
            if len(result) >= self.tag_count_min:
                break
            cleaned = candidate.strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)

        return result[: self.tag_count_max]

    def generate_metadata(self, script: Script) -> Metadata:
        prompt = self._build_prompt(script)
        raw = self.client.generate_json(prompt=prompt, temperature=0.7)
        return Metadata(
            title=self._normalize_title(raw.get("title") or ""),
            description=self._build_description(raw, script),
            tags=self._normalize_tags(raw.get("tags") or [], script),
            category=self.category_id,
        )
