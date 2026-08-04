import os
import json
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv


class Config:
    def __init__(self, settings_path: str = "config/settings.json"):
        load_dotenv()
        
        self.settings_path = Path(settings_path)
        self.settings = self._load_settings()
        self._load_env_secrets()
    
    def _load_settings(self) -> Dict[str, Any]:
        if not self.settings_path.exists():
            raise FileNotFoundError(f"Settings file not found: {self.settings_path}")
        
        with open(self.settings_path, 'r') as f:
            return json.load(f)
    
    def _load_env_secrets(self):
        self.settings['api_keys']['groq_api_key'] = os.getenv('GROQ_API_KEY', '')
        self.settings['api_keys']['youtube_client_id'] = os.getenv('YOUTUBE_CLIENT_ID', '')
        self.settings['api_keys']['youtube_client_secret'] = os.getenv('YOUTUBE_CLIENT_SECRET', '')
        self.settings['api_keys']['reddit_client_id'] = os.getenv('REDDIT_CLIENT_ID', '')
        self.settings['api_keys']['reddit_client_secret'] = os.getenv('REDDIT_CLIENT_SECRET', '')
    
    def get(self, *keys: str, default: Any = None) -> Any:
        value = self.settings
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def __getitem__(self, key: str) -> Any:
        return self.settings[key]


_config_instance = None

def get_config(settings_path: str = "config/settings.json") -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(settings_path)
    return _config_instance
