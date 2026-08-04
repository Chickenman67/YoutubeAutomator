import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import get_config


def main():
    parser = argparse.ArgumentParser(
        description='YouTube Automation System - Generate educational videos automatically'
    )
    
    parser.add_argument(
        '--config',
        default='config/settings.json',
        help='Path to settings.json configuration file'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    subparsers.add_parser('generate', help='Generate a new video from topic selection through queue')
    subparsers.add_parser('dashboard', help='Start the review dashboard web interface')
    subparsers.add_parser('upload', help='Upload approved videos to YouTube')
    subparsers.add_parser('config', help='Show current configuration')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    config = get_config(args.config)
    
    if args.command == 'config':
        print("Configuration loaded successfully:")
        print(f"  Settings file: {config.settings_path}")
        print(f"  Groq API key: {'[Set]' if config.get('api_keys', 'groq_api_key') else '[Missing]'}")
        print(f"  YouTube credentials: {'[Set]' if config.get('api_keys', 'youtube_client_id') else '[Missing]'}")
        print(f"  NewsAPI key: {'[Set]' if config.get('api_keys', 'newsapi_api_key') else '[Missing]'}")
        print(f"  Video target length: {config.get('video', 'target_length_min')}-{config.get('video', 'target_length_max')} minutes")
        print(f"  Scene count: {config.get('video', 'scene_count_min')}-{config.get('video', 'scene_count_max')} scenes")
    
    elif args.command == 'generate':
        print("Generate command not yet implemented (future tickets)")
    
    elif args.command == 'dashboard':
        print("Dashboard command not yet implemented (future tickets)")
    
    elif args.command == 'upload':
        print("Upload command not yet implemented (future tickets)")


if __name__ == '__main__':
    main()
