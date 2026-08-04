# Youtube Automator

Automated pipeline for generating daily educational YouTube videos with trending and evergreen topics, producing mid-form videos with extracted Shorts for multi-platform distribution.

## Features

- **Topic selection**: 70% trending topics (Wikipedia/Reddit) + 30% curated evergreen topics, with anti-repeat rotation
- **Script generation**: LLM-generated humanized scripts with scene structure and fact-checking
- **Video production**: Character-based Manim animations + Edge TTS voiceovers, assembled into mid-form + Short videos
- **Metadata**: Auto-generated SEO-optimized titles, descriptions, timestamps, and tags
- **Review dashboard**: Local web interface to preview and approve/reject videos before upload
- **YouTube upload**: Batch upload approved videos via the YouTube Data API

## Requirements

- Python 3.10+
- FFmpeg (required by MoviePy and Edge TTS)
- [Groq API key](https://console.groq.com) for LLM generation (free tier available)
- [YouTube API credentials](https://console.cloud.google.com/apis/credentials) (free, 10k units/day)
- Optional: Reddit API credentials for trending topics

## Installation

1. Clone the repository and enter the directory

2. Create and activate a virtual environment:

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python -m venv venv
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Install FFmpeg if not already present:

```bash
# Windows (via winget)
winget install Gyan.FFmpeg

# macOS
brew install ffmpeg

# Linux (Debian/Ubuntu)
sudo apt install ffmpeg
```

5. Configure API keys:

```bash
# Copy the example environment file
cp .env.example .env
```

Edit `.env` and fill in your API keys. The `config/settings.json` file controls system behavior (thresholds, video dimensions, scene counts).

## Usage

```bash
# Show current configuration
python main.py config

# Generate a video (topic → script → queue)
python main.py generate

# Start the review dashboard
python main.py dashboard

# Upload approved videos to YouTube
python main.py upload
```

## Project Structure

```
├── src/
│   ├── __main__.py          # CLI entry point
│   ├── config.py            # Configuration loader
│   ├── topic_selection/     # Trending + evergreen topic selection
│   ├── script_generation/   # LLM script generation + fact-checking
│   ├── video_production/    # Manim animations + MoviePy editing
│   ├── metadata/            # Title/description/tags generation
│   ├── upload/              # YouTube API integration
│   └── dashboard/           # Review interface
├── config/
│   └── settings.json        # System configuration
├── queue/
│   ├── pending_review/      # Videos awaiting approval
│   ├── approved/            # Ready to upload
│   ├── rejected/            # Rejected, needs manual review
│   └── uploaded/            # Upload complete
├── topics/
│   └── evergreen.json       # Curated topic pool
└── tests/                   # Test suite
```

## Testing

```bash
pytest
```

## Roadmap

This is a work in progress. Individual tickets track the build under GitHub Issues. See the [spec](docs/spec.md) for the full design.
