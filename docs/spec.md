# YouTube Automation System - Specification

## Problem Statement

Creating daily educational YouTube videos manually is time-consuming and unsustainable. Content creators need to research topics, write scripts, generate voiceovers, create visuals, edit videos, generate thumbnails, write metadata, and upload — all of which can take 4-6 hours per video. For daily production (30 videos/month), this workload is unrealistic for a solo creator.

Additionally, trending topics offer viral potential but require fast turnaround to capitalize on peak interest. Manual production can't keep pace with trending cycles.

## Solution

An automated pipeline that generates educational videos from topic selection through upload-ready assets, with human review checkpoints. The system produces one 5-10 minute mid-form video daily, automatically extracting 3-5 Shorts from each. It balances trending topics (70%) for viral potential with evergreen curated content (30%) for consistent quality.

The pipeline is semi-automated: generates complete videos with all assets, queues them for user review, then uploads approved content. This allows quality control while removing 90%+ of manual production work.

## User Stories

1. As a content creator, I want the system to identify trending topics automatically, so that I can capitalize on viral interest without manual research
2. As a content creator, I want trending topics filtered for educational value, so that my content stays monetization-safe and on-brand
3. As a content creator, I want an engagement threshold that auto-adjusts, so that I always have enough topics even on slow news days
4. As a content creator, I want a curated evergreen topic pool, so that I have consistent backup content when trending topics are weak
5. As a content creator, I want 90-day topic rotation, so that I never accidentally repeat content
6. As a content creator, I want scripts written in humanized natural language, so that my videos don't sound robotic or get flagged by AI detectors
7. As a content creator, I want scripts structured as discrete scenes, so that each scene can become a standalone Short
8. As a content creator, I want automatic fact-checking of scripts, so that I catch errors before publishing
9. As a content creator, I want fact-check confidence scores, so that I know which claims need manual verification
10. As a content creator, I want voiceovers generated automatically, so that I don't need to record narration daily
11. As a content creator, I want unlimited voiceover generation, so that I can produce daily content without quota limits
12. As a content creator, I want character-based animations, so that videos are more engaging than stock footage slideshows
13. As a content creator, I want stick figure animations, so that production is fast and visuals work across all topics
14. As a content creator, I want scene-based video structure, so that the same production pipeline creates both mid-form and Shorts
15. As a content creator, I want automatic video editing, so that I don't spend hours in editing software
16. As a content creator, I want automatic Short extraction, so that I get 3-5 Shorts from each mid-form video without extra work
17. As a content creator, I want automatic thumbnail generation, so that every video has a thumbnail without manual design
18. As a content creator, I want thumbnails with text overlays, so that they're clickable and communicate the topic clearly
19. As a content creator, I want automatic metadata generation, so that titles, descriptions, and tags are SEO-optimized
20. As a content creator, I want metadata optimized for discoverability, so that my videos get recommended by YouTube's algorithm
21. As a content creator, I want a review dashboard, so that I can preview videos before they go live
22. As a content creator, I want to see scripts and fact-check results during review, so that I can verify quality and accuracy
23. As a content creator, I want to approve or reject videos with one click, so that review is fast
24. As a content creator, I want a folder-based queue system, so that I can see video status at a glance
25. As a content creator, I want approved videos to upload automatically, so that I don't manually upload 30 videos per month
26. As a content creator, I want the YouTube API to handle uploads, so that I can schedule and batch uploads programmatically
27. As a content creator, I want all tools to be 100% free, so that I can run this system without monthly costs
28. As a content creator, I want the system to be semi-automated now, so that I maintain quality control during the refinement phase
29. As a content creator, I want a path to full automation later, so that the system can run unattended once scripts are refined
30. As a content creator, I want topic categories to include history, science, geography, culture, and phenomena, so that content isn't limited to school subjects

## Implementation Decisions

### Architecture

- **Language**: Python (best ecosystem for media processing, TTS, API integrations)
- **Folder structure**:
  ```
  /
  ├── src/
  │   ├── topic_selection/     # Trending + evergreen topic selection
  │   ├── script_generation/   # LLM script generation + fact-checking
  │   ├── video_production/    # Manim animations + MoviePy editing
  │   ├── metadata/            # Title/description/tags generation
  │   ├── upload/              # YouTube API integration
  │   └── dashboard/           # Review interface
  ├── topics/
  │   └── evergreen.json       # Curated topic pool
  ├── queue/
  │   ├── pending_review/      # Videos awaiting approval
  │   ├── approved/            # Ready to upload
  │   └── uploaded/            # Upload complete
  ├── config/
  │   └── settings.json        # API keys, thresholds, preferences
  └── tests/
  ```

### Topic Selection Module

- **Trending sources**: Wikipedia trending pages API + Reddit r/todayilearned top posts
- **Dynamic threshold**: Start at 50k Wikipedia views / 5k Reddit upvotes, adjust down (20k/2k, then 10k/1k) if fewer than 3 topics found, adjust up if more than 10 topics found
- **Explainability filter**: LLM quick-check prompt: "Can this be explained in a 5-10 minute educational video with verifiable facts? Yes/No + 1-sentence reason"
- **70/30 split**: Select 5 trending topics + 2 evergreen topics per week (daily production)
- **Evergreen rotation**: Track usage timestamps in JSON, exclude topics used within 90 days
- **Output format**: JSON with topic, source, category, engagement_score, explainability_reason

### Script Generation Module

- **LLM**: Groq free tier (Llama 3.1 70B) for all text generation
- **Humanization**: Adapt GeneralWriterPrompt.md for video narration:
  - Keep: contractions, varied rhythm, concrete details, no AI clichés
  - Adjust: simpler sentences (spoken word), no visual punctuation (em dashes, semicolons), conversational tone
  - Store adapted prompt as `config/video_script_prompt.txt`
- **Scene structure**: Generate scripts as JSON array of scenes, each with:
  - `scene_id`: int
  - `narration`: string (60-90 seconds when spoken)
  - `key_visual_keywords`: array of strings (for Manim animation)
  - `facts`: array of factual claims to validate
- **Fact-checking**: Extract claims from each scene, validate against Wikipedia API, return confidence scores (high/medium/low), flag low-confidence claims in review
- **Target length**: Mid-form = 5-7 scenes (5-10 min total), each scene becomes one Short

### Video Production Module

- **Animation library**: Manim Community Edition (actively maintained, Python-native)
- **Visual style**: Stick figures + simple geometric icons, black-and-white or minimal color
- **Scene rendering**: For each scene:
  1. Generate Manim animation script from `key_visual_keywords`
  2. Render scene to video file (1080x1920 vertical for Shorts compatibility)
  3. Generate voiceover from narration text
  4. Combine animation + voiceover with MoviePy
- **TTS**: Edge TTS (edge-tts Python library), unlimited free, Microsoft voices
- **Mid-form assembly**: Stitch all scenes with MoviePy, add transitions (1s fade), export as 1080p MP4
- **Short extraction**: Each scene is already a standalone 60-90s video, export separately as vertical 1080x1920 MP4
- **Thumbnail generation**: Extract frame from mid-form video (scene 1 at 3s), add text overlay (Pillow), bold sans-serif font, high contrast

### Metadata Generation Module

- **Title generation**: LLM prompt: "Write a YouTube-optimized title for this educational video (max 60 chars, include main keyword, create curiosity)"
- **Description generation**: Template with dynamic fields:
  - Script summary (2-3 sentences)
  - Timestamps for each scene (for mid-form)
  - Standard footer (social links, upload schedule)
- **Tags**: Extract 10-15 relevant keywords from script + topic category
- **Category**: YouTube category ID 27 (Education)

### Upload Module

- **YouTube Data API v3**: Official Python client library
- **Authentication**: OAuth 2.0 (one-time manual auth, store refresh token)
- **Quota management**: 10k units/day free, upload = 1600 units, monitor daily usage
- **Batch upload**: Process all videos in `approved/` folder
- **Metadata**: Set title, description, tags, category, privacy (public/unlisted/scheduled)
- **Error handling**: Retry failed uploads (rate limit, network errors), log failures

### Review Dashboard

- **Technology**: Local HTML + JavaScript (Flask backend for file serving)
- **Features**:
  - List all pending videos with preview thumbnails
  - Click to expand: video player, full script, fact-check results, metadata
  - Approve button: moves video from `pending_review/` to `approved/`
  - Reject button: moves video to `rejected/` (manual review needed)
  - Bulk actions: approve/reject multiple videos
- **Runs locally**: `python src/dashboard/app.py`, opens browser to `localhost:5000`

### Configuration Management

- **settings.json** contains:
  - API keys (Groq, YouTube)
  - Trending thresholds (Wikipedia views, Reddit upvotes)
  - Topic split ratio (70/30)
  - Evergreen rotation days (90)
  - Video target length (5-10 min)
  - Scene length (60-90 sec)
- **Environment variables** for secrets (Groq API key, YouTube credentials)

### Data Storage

- **No database**: All state managed via filesystem and JSON files
- **Topic pool**: `topics/evergreen.json` with structure:
  ```json
  {
    "topics": [
      {
        "id": 1,
        "text": "The Fall of the Roman Empire",
        "category": "history",
        "last_used": "2026-05-15",
        "times_used": 2
      }
    ]
  }
  ```
- **Video metadata**: Each video in queue has accompanying JSON file with all metadata, fact-check results, source topic

## Testing Decisions

### What Makes a Good Test

- Test external behavior, not implementation details
- Mock external APIs (Groq, Wikipedia, YouTube) to avoid flaky network-dependent tests
- Use fixture data (sample topics, scripts) to ensure reproducible tests
- Test edge cases (empty topic pool, API failures, malformed responses)

### Modules to Test

1. **Topic Selection Module** (`src/topic_selection/selector.py`):
   - Test trending filter with mock Wikipedia/Reddit data
   - Test explainability scoring with mock LLM responses
   - Test dynamic threshold adjustment (too few/too many topics)
   - Test evergreen rotation (exclude recently used topics)
   - Test 70/30 split logic

2. **Script Generation Module** (`src/script_generation/generator.py`):
   - Test scene structure (correct JSON format, 5-7 scenes)
   - Test humanization prompt inclusion (verify contractions, varied rhythm in output)
   - Test fact extraction from narration
   - Test Wikipedia validation (mock API responses)
   - Test confidence scoring logic

3. **Video Production Module** (`src/video_production/producer.py`):
   - Test scene rendering (Manim generates valid video files)
   - Test voiceover generation (Edge TTS produces audio files)
   - Test audio-video sync (voiceover matches scene duration)
   - Test mid-form stitching (all scenes combined, transitions added)
   - Test Short extraction (each scene exported as vertical video)
   - Test thumbnail generation (image file created, text overlay present)

4. **Metadata Generation Module** (`src/metadata/generator.py`):
   - Test title length constraint (max 60 chars)
   - Test description structure (summary + timestamps + footer)
   - Test tag extraction (relevant keywords from script)
   - Test category assignment

5. **Upload Module** (`src/upload/uploader.py`):
   - Test YouTube API calls (mocked, verify request format)
   - Test retry logic (handle rate limits, network errors)
   - Test quota tracking (don't exceed 10k units/day)
   - Test batch upload (process multiple approved videos)

6. **End-to-End Pipeline Test**:
   - Given a sample topic, run full pipeline (topic → script → video → queue)
   - Verify all assets created (mid-form MP4, Short MP4s, thumbnail PNG, metadata JSON)
   - Verify video in `pending_review/` folder
   - Do NOT upload (stop before YouTube API call)

### Prior Art

- No existing tests in codebase (greenfield project)
- Follow Python testing conventions: pytest framework, fixtures in `tests/fixtures/`, mocks with `unittest.mock`

## Out of Scope

- **Manual editing tools**: No built-in video editor for tweaking animations or timing (use external tools if needed)
- **Multi-platform upload**: Only YouTube initially (TikTok, Instagram, etc. can be added later)
- **Advanced analytics**: No view tracking, A/B testing, or performance dashboards (use YouTube Studio)
- **Custom voiceover models**: Stick with Edge TTS, no custom voice cloning or training
- **Advanced Manim features**: No 3D animations, complex mathematical visualizations, or interactive elements
- **Content moderation**: No automated profanity filters, controversy detection, or sensitivity checks (rely on fact-checking + human review)
- **Monetization tracking**: No revenue analytics, sponsorship management, or affiliate link insertion
- **Collaboration features**: Single-user system, no multi-user review workflows or permissions
- **Mobile app**: Dashboard is web-based but desktop-optimized, no native mobile interface

## Further Notes

### Path to Full Automation

The system is designed to support full automation later:
- Replace review dashboard approval with auto-approval logic (confidence score thresholds)
- Add scheduled upload (cron job runs daily, processes queue automatically)
- Keep manual review as optional override (flag videos for review based on criteria)

### Scaling Considerations

Current design supports daily production (30 videos/month). To scale to multiple videos/day:
- Increase Groq API quota (monitor rate limits)
- Parallelize video production (render multiple videos concurrently)
- Add upload scheduling to spread throughout day (avoid quota spikes)

### Quality Refinement

After initial production, monitor for patterns in rejected videos:
- Adjust explainability prompt if wrong topics pass filter
- Refine humanization prompt if scripts sound too robotic
- Tune fact-checking thresholds if too many false positives/negatives
- Iterate on Manim visual templates based on engagement data

### Initial Seed Data

System ships with 100 pre-populated evergreen topics across categories:
- 30 history (ancient civilizations, wars, historical figures)
- 25 science (space, biology, physics discoveries)
- 20 geography (countries, natural wonders, cities)
- 15 culture (traditions, art movements, festivals)
- 10 phenomena (psychological effects, natural events, social patterns)

User can edit `topics/evergreen.json` anytime to add/remove/modify topics.
