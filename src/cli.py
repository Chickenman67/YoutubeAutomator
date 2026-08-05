import argparse
import sys
import webbrowser

from config import get_config
from dashboard.app import create_app
from upload.auth import AuthError, build_client, get_credentials
from upload.uploader import YouTubeUploader


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
    generate = subparsers.add_parser('generate', help='Generate scripts for new videos')
    generate.add_argument('--topic', default=None, help='Generate for a specific topic instead of selecting')
    generate.add_argument('--count', type=int, default=1, help='Number of topics to process when selecting')
    dashboard = subparsers.add_parser('dashboard', help='Start the review dashboard web interface')
    dashboard.add_argument('--queue-root', default=None, help='Root of the queue directory (default: paths.queue_root -> queue)')
    dashboard.add_argument('--host', default='127.0.0.1', help='Host interface to bind (default: 127.0.0.1)')
    dashboard.add_argument('--port', type=int, default=5000, help='Port to serve on (default: 5000)')
    dashboard.add_argument('--no-browser', action='store_true', help='Do not open a browser automatically')
    upload = subparsers.add_parser('upload', help='Upload approved videos to YouTube')
    upload.add_argument('--queue-root', default=None, help='Root of the queue directory (default: paths.queue_root -> queue)')
    upload.add_argument('--publish-at', default=None, help='ISO datetime to schedule publication (privacy forced to private)')
    upload.add_argument('--token-path', default=None, help='Path to the stored OAuth token (default: paths.youtube_token -> config/youtube_token.json)')
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
    machine = build_state_machine(config)
    if args.topic:
        topics = [args.topic]
    else:
        topics = machine.select_topics()[: args.count]
    for topic in topics:
        result = machine.run_video(topic)
        print(result.to_json())
    return 0


def build_state_machine(config):
    from fact_check.fact_checker import FactChecker
    from llm import GroqClient
    from metadata.generator import MetadataGenerator
    from pipeline.state_machine import PipelineStateMachine
    from script_generation.generator import ScriptGenerator
    from topic_selection.selector import TopicSelector

    api_key = config.get("api_keys", "groq_api_key", default="") or ""
    groq = GroqClient(api_key=api_key) if api_key else None
    selector = TopicSelector.from_config(config)
    return PipelineStateMachine(
        topic_selector=selector,
        script_generator=ScriptGenerator(groq),
        fact_checker=FactChecker(),
        metadata_generator=MetadataGenerator(groq),
    )


def cmd_dashboard(config, args):
    queue_root = args.queue_root or config.get("paths", "queue_root", default="queue")
    app = create_app(queue_root=queue_root)
    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        webbrowser.open(url)
    app.run(host=args.host, port=args.port)
    return 0


def cmd_upload(config, args):
    token_path = args.token_path or config.get("paths", "youtube_token", default="config/youtube_token.json")
    client_id = config.get("api_keys", "youtube_client_id", default="") or ""
    client_secret = config.get("api_keys", "youtube_client_secret", default="") or ""
    try:
        credentials = get_credentials(token_path, client_id, client_secret)
    except AuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    client = build_client(credentials)
    queue_root = args.queue_root or config.get("paths", "queue_root", default="queue")
    uploader = YouTubeUploader.from_config(
        config, client=client, queue_root=queue_root, publish_at=args.publish_at
    )
    batch = uploader.upload_batch()
    print(batch.to_json())
    return 0
