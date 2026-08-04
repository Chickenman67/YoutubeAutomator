from typing import List, Dict, Any
from dataclasses import dataclass, asdict
import json


@dataclass
class Scene:
    scene_id: int
    narration: str
    key_visual_keywords: List[str]
    facts: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Scene':
        return cls(**data)


@dataclass
class Script:
    topic: str
    scenes: List[Scene]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'topic': self.topic,
            'scenes': [scene.to_dict() for scene in self.scenes]
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Script':
        return cls(
            topic=data['topic'],
            scenes=[Scene.from_dict(s) for s in data['scenes']]
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Script':
        return cls.from_dict(json.loads(json_str))
    
    def validate(self) -> List[str]:
        errors = []
        min_scenes, max_scenes = 5, 7
        min_keywords, max_keywords = 3, 5
        min_facts, max_facts = 2, 4
        min_words, max_words = 200, 400
        
        if not self.topic:
            errors.append("Topic is required")
        
        if len(self.scenes) < min_scenes or len(self.scenes) > max_scenes:
            errors.append(f"Script should have {min_scenes}-{max_scenes} scenes, got {len(self.scenes)}")
        
        for i, scene in enumerate(self.scenes):
            if scene.scene_id != i + 1:
                errors.append(f"Scene {i+1} has incorrect scene_id: {scene.scene_id}")
            
            word_count = len(scene.narration.split())
            if word_count < min_words or word_count > max_words:
                errors.append(f"Scene {i+1} narration has {word_count} words, expected {min_words}-{max_words} (60-90 sec spoken)")
            
            if not scene.key_visual_keywords:
                errors.append(f"Scene {i+1} missing key_visual_keywords")
            elif len(scene.key_visual_keywords) < min_keywords or len(scene.key_visual_keywords) > max_keywords:
                errors.append(f"Scene {i+1} has {len(scene.key_visual_keywords)} visual keywords, expected {min_keywords}-{max_keywords}")
            
            if not scene.facts:
                errors.append(f"Scene {i+1} missing facts array")
            elif len(scene.facts) < min_facts or len(scene.facts) > max_facts:
                errors.append(f"Scene {i+1} has {len(scene.facts)} facts, expected {min_facts}-{max_facts}")
        
        return errors
