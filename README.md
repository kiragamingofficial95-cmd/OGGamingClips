# OGGamingClips — Automated Short-Form Clipping System

Production-ready system that generates **10+ short-form gaming clips per day** from campaign-authorized footage for Instagram.

## Overview

This pipeline processes authorized video sources through:

1. **Input** — Register source videos from folder, URL, or API
2. **Transcription** — Whisper extracts timestamped audio transcripts
3. **AI Analysis** — Groq identifies clip-worthy moments
4. **Clip Selection** — Rank and deduplicate candidates
5. **Video Editing** — FFmpeg cuts, converts to 9:16, adds subtitles
6. **Metadata** — Generate titles, captions, hashtags
7. **Quality Control** — Verify output and handle failures
8. **Dashboard** — Track progress via FastAPI

## Quick Start

```bash
# 1. Copy env file
cp .env.example .env
# Edit .env with your credentials

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run migrations
python -m app.database.migrations

# 4. Start worker + API
python -m app.main

# 5. Or run API only
python -m app.main api

# 6. Or run worker only
python -m app.main worker
```

## Docker

```bash
docker-compose up --build
```

## Railway Deployment

1. Connect PostgreSQL and Redis services on Railway
2. Set all environment variables in Railway dashboard
3. Connect GitHub repo — Railway auto-deploys
4. Worker runs continuously

## Project Structure

```
app/
├── main.py                     # Entry point (worker + API)
├── config.py                   # Environment-driven config
├── database/
│   ├── connection.py           # PostgreSQL async pool
│   └── migrations.py           # Schema creation
├── models/
│   ├── source.py               # Source video model
│   ├── transcript.py           # Transcript model
│   └── clip.py                 # Clip & candidate models
├── workers/
│   └── pipeline_worker.py      # Main processing loop
├── services/
│   ├── transcription/
│   │   └── whisper_service.py  # Whisper audio → text
│   ├── groq/
│   │   └── analysis_service.py # Groq AI clip detection
│   ├── video/
│   │   └── ffmpeg_service.py   # FFmpeg clip editing
│   ├── storage/
│   │   └── storage_service.py  # Local/S3 storage
│   └── metadata/
│       └── metadata_generator.py # Titles, captions, tags
├── api/
│   ├── app.py                  # FastAPI dashboard
│   └── routes/
└── utils/
    ├── retry.py                # Exponential backoff
    ├── validators.py           # Input validation
    └── logger.py               # Structured logging
tests/
├── test_transcription.py
├── test_groq.py
├── test_pipeline.py
└── test_video.py
```

## Configuration

All settings are in `.env` or environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DAILY_CLIP_TARGET` | 10 | Clips per day |
| `MIN_CLIP_SCORE` | 7.0 | Minimum AI score |
| `MIN_CLIP_DURATION` | 20 | Min seconds |
| `MAX_CLIP_DURATION` | 60 | Max seconds |
| `GROQ_API_KEY` | - | Groq API key |
| `DATABASE_URL` | - | PostgreSQL connection |
| `REDIS_URL` | - | Redis connection |
| `STORAGE_PROVIDER` | local | local/s3/gcs |

## API Endpoints

- `GET /health` — Health check
- `GET /dashboard` — Today's overview
- `GET /dashboard/clips` — List clips
- `GET /dashboard/sources` — List sources
- `GET /dashboard/failed` — Failed jobs
- `GET /dashboard/errors` — Recent errors
- `GET /dashboard/candidates` — Clip candidates
- `GET /stats` — Detailed statistics
- `POST /sources/register` — Register a source
- `POST /sources/discover` — Auto-discover sources

## Cost Control

- Transcripts are cached and never re-sent to Groq
- AI analysis runs on chunks, not entire videos
- Results cached in-memory and in database
- Groq API calls are protected by retry with backoff

## Security

- All secrets via environment variables
- Never commit `.env`
- Input validation on all external data
- Campaign authorization enforced before processing
- Only authorized sources are processed

## License

Internal use only. Content must be authorized by campaign owner.
