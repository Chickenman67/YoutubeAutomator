import argparse
import sys

from config import get_config


def build_parser():
    parser = argparse.ArgumentParser(
        description='YouTube Automation System - Generate educational videos automatically'
    )
    parser.add_argument(
        '--config',
        default='config/settings.json',
        help='Path to settings.json configuration file'
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    subparsers.add_parser('generate', help='Generate scripts for new videos')
    subparsers.add_parser('dashboard', help='Start the review dashboard web interface')
    subparsers.add_parser('upload', help='Upload approved videos to YouTube')
    subparsers.add_parser('config', help='Show current configuration')
    return parser


def cmd_config(config, args):
    print("Configuration loaded successfully:")
    print(f"  Settings file: {config.settings_path}")
    print(f"  Groq API key: {'[Set]' if config.get('api_keys', 'groq_api_key') else '[Missing]'}")
    print(f"  YouTube credentials: {'[Set]' if config.get('api_keys', 'youtube_client_id') else '[Missing]'}")
    print(f"  NewsAPI key: {'[Set]' if config.get('api_keys', 'newsapi_api_key') else '[Missing]'}")
    print(f"  Video target length: {config.get('video', 'target_length_min')}-{config.get('video', 'target_length_max')} minutes")
    print(f"  Scene count: {config.get('video', 'scene_count_min')}-{config.get('video', 'scene_count_max')} scenes")
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    try:
        config = get_config(args.config)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == 'config':
            return cmd_config(config, args)
        if args.command == 'generate':
            return cmd_generate(config, args)
        if args.command == 'dashboard':
            return cmd_dashboard(config, args)
        if args.command == 'upload':
            return cmd_upload(config, args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_generate(config, args):
    return 0


def cmd_dashboard(config, args):
    return 0


def cmd_upload(config, args):
    return 0
