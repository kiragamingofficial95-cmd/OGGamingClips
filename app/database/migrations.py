"""Database schema migrations — creates all required tables."""
from app.database.connection import execute
from app.utils.logger import get_logger

logger = get_logger("migrations")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key      TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'file',
    url             TEXT,
    file_path       TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    is_authorized   BOOLEAN NOT NULL DEFAULT TRUE,
    campaign_id     TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transcripts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    transcript_path TEXT,
    content         JSONB NOT NULL DEFAULT '[]',
    language        TEXT DEFAULT 'en',
    duration_seconds NUMERIC,
    word_count      INTEGER,
    status          TEXT NOT NULL DEFAULT 'pending',
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clip_candidates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    transcript_id   UUID REFERENCES transcripts(id),
    start_time      NUMERIC NOT NULL,
    end_time        NUMERIC NOT NULL,
    score           NUMERIC NOT NULL DEFAULT 0,
    hook            TEXT,
    reason          TEXT,
    suggested_title TEXT,
    metadata        JSONB DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending',
    is_duplicate    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clips (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    candidate_id    UUID REFERENCES clip_candidates(id),
    clip_path       TEXT,
    storage_url     TEXT,
    title           TEXT,
    caption         TEXT,
    hashtags        TEXT[],
    duration_seconds NUMERIC,
    resolution      TEXT,
    file_size_bytes BIGINT,
    ai_score        NUMERIC,
    status          TEXT NOT NULL DEFAULT 'pending',
    error           TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID REFERENCES sources(id) ON DELETE CASCADE,
    job_type        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued',
    progress        NUMERIC DEFAULT 0,
    error           TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 3,
    metadata        JSONB DEFAULT '{}',
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_stats (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE NOT NULL UNIQUE,
    clips_generated INTEGER NOT NULL DEFAULT 0,
    clips_target    INTEGER NOT NULL DEFAULT 10,
    clips_failed    INTEGER NOT NULL DEFAULT 0,
    sources_processed INTEGER NOT NULL DEFAULT 0,
    total_candidates INTEGER NOT NULL DEFAULT 0,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sources_key ON sources(source_key);
CREATE INDEX IF NOT EXISTS idx_sources_campaign ON sources(campaign_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_source ON transcripts(source_id);
CREATE INDEX IF NOT EXISTS idx_candidates_source ON clip_candidates(source_id);
CREATE INDEX IF NOT EXISTS idx_candidates_score ON clip_candidates(score DESC);
CREATE INDEX IF NOT EXISTS idx_clips_source ON clips(source_id);
CREATE INDEX IF NOT EXISTS idx_clips_status ON clips(status);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON processing_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(date);
"""


async def run_migrations():
    logger.info("Running database migrations...")
    await execute(SCHEMA_SQL)
    logger.info("All migrations applied successfully")
