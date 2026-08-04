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
        
        if not self.topic:
            errors.append("Topic is required")
        
        if not self.scenes:
            errors.append("Script must have at least one scene")
        
        if len(self.scenes) < 5 or len(self.scenes) > 7:
            errors.append(f"Script should have 5-7 scenes, got {len(self.scenes)}")
        
        for i, scene in enumerate(self.scenes):
            if scene.scene_id != i + 1:
                errors.append(f"Scene {i+1} has incorrect scene_id: {scene.scene_id}")
            
            if not scene.narration or len(scene.narration.strip()) < 50:
                errors.append(f"Scene {i+1} narration is too short (min 50 chars for 60-90 sec spoken)")
            
            if not scene.key_visual_keywords:
                errors.append(f"Scene {i+1} missing key_visual_keywords")
            
            if not scene.facts:
                errors.append(f"Scene {i+1} missing facts array")
        
        return errors
