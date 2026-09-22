"""Main pipeline worker that orchestrates the clip generation process."""
import asyncio
import json
import os
import uuid
from datetime import datetime, date
from typing import Optional, List, Dict
from pathlib import Path

from app.config import get_settings
from app.database.connection import get_pool, close_pool
from app.database.migrations import run_migrations
from app.models.source import Source
from app.models.transcript import Transcript
from app.models.clip import Clip, ClipCandidate
from app.services.groq import GroqAnalysisService
from app.services.video import FFmpegService
from app.services.storage import StorageService
from app.services.metadata import MetadataGenerator
from app.utils.retry import retry_with_backoff
from app.utils.logger import get_logger
from app.utils.validators import validate_source_path, validate_campaign_id

logger = get_logger("worker")
settings = get_settings()


class PipelineWorker:
    def __init__(self):
        self._transcriber = None
        self.groq = GroqAnalysisService()
        self.ffmpeg = FFmpegService()
        self.storage = StorageService()
        self.metadata_gen = MetadataGenerator()
        self.running = False
        self._daily_count = 0
        self._today = date.today().isoformat()

    @property
    def transcriber(self):
        # Groq Whisper API: no local torch needed, works on Railway free tier
        if self._transcriber is None:
            from app.services.transcription import GroqTranscriptionService
            self._transcriber = GroqTranscriptionService()
        return self._transcriber

    @property
    def whisper(self):
        # Backwards-compatible alias
        return self.transcriber

    async def start(self):
        """Start the pipeline worker."""
        self.running = True
        logger.info("Pipeline worker starting", target=settings.DAILY_CLIP_TARGET)

        await run_migrations()

        while self.running:
            try:
                await self._process_cycle()
                await self._check_daily_target()
            except asyncio.CancelledError:
                logger.info("Worker cancelled, shutting down gracefully")
                break
            except Exception as e:
                logger.error("Worker cycle error", error=str(e))
                await asyncio.sleep(settings.WORKER_POLL_INTERVAL)

        await close_pool()
        logger.info("Pipeline worker stopped")

    async def stop(self):
        """Graceful shutdown."""
        self.running = False
        logger.info("Worker stop signal received")

    async def _process_cycle(self):
        """One processing cycle: find sources, process them, generate clips."""
        pool = await get_pool()

        sources = await pool.fetch("""
            SELECT * FROM sources 
            WHERE status IN ('pending', 'queued') 
            AND is_authorized = TRUE
            ORDER BY created_at ASC
            LIMIT $1
        """, settings.WORKER_MAX_CONCURRENT)

        if not sources:
            logger.info("No pending sources found")
            await asyncio.sleep(settings.WORKER_POLL_INTERVAL)
            return

        for source_row in sources:
            if not self.running:
                break
            source = Source.from_db(source_row)
            await self._process_source(source)

    async def _process_source(self, source: Source):
        """Process a single source video through the full pipeline."""
        logger.info("Processing source", source_id=source.source_key, name=source.name)

        await self._update_source_status(source.id, "processing")
        job_id = await self._create_job(source.id, "full_pipeline")

        try:
            transcript = await self._run_transcription(source)
            candidates = await self._run_analysis(source.id, transcript)
            selected = await self._select_clips(candidates, source.id)
            completed_clips = await self._run_video_editing(source, selected)
            await self._update_daily_stats(len(completed_clips))
            await self._update_source_status(source.id, "completed")
            await self._complete_job(job_id)
            logger.info("Source processing complete", source_id=source.source_key, clips=len(completed_clips))
        except Exception as e:
            logger.error("Source processing failed", source_id=source.source_key, error=str(e))
            await self._mark_job_failed(job_id, str(e))
            await self._update_source_status(source.id, "failed")

    async def _run_transcription(self, source: Source) -> Transcript:
        """Run Whisper transcription on a source."""
        source_path = source.file_path
        if not source_path or not validate_source_path(source_path):
            raise ValueError(f"Invalid source path: {source_path}")

        existing = await self._get_existing_transcript(source.id)
        if existing:
            logger.info("Using existing transcript", source_id=source.source_key)
            return existing

        result = await retry_with_backoff(
            lambda: self.whisper.transcribe(source_path, str(source.id)),
            max_retries=settings.WORKER_MAX_RETRIES,
            base_delay=settings.WORKER_RETRY_BACKOFF,
        )

        transcript_id = uuid.uuid4()
        await self._save_transcript_to_db(transcript_id, source.id, result)
        logger.info("Transcription saved to DB", source_id=source.source_key, segments=len(result["segments"]))

        return Transcript(
            id=transcript_id,
            source_id=source.id,
            transcript_path=result.get("transcript_path", ""),
            content=result["segments"],
            language=result["language"],
            duration_seconds=result["duration_seconds"],
            word_count=result["word_count"],
            status="completed",
        )

    async def _run_analysis(self, source_id: uuid.UUID, transcript: Transcript) -> List[Dict]:
        """Run Groq analysis on transcript."""
        cached = self.groq.get_cached_analysis(transcript.content)
        if cached is not None:
            logger.info("Using cached analysis", source_id=source_id)
            return cached

        candidates = await retry_with_backoff(
            lambda: self.groq.analyze_candidates(
                transcript.content,
                str(source_id),
            ),
            max_retries=settings.WORKER_MAX_RETRIES,
            base_delay=settings.WORKER_RETRY_BACKOFF,
        )

        await self._save_candidates_to_db(source_id, transcript.id, candidates)
        logger.info("Candidates saved", source_id=source_id, count=len(candidates))
        return candidates

    async def _select_clips(self, candidates: List[Dict], source_id: uuid.UUID) -> List[ClipCandidate]:
        """Select best clips ensuring no overlaps and daily limits."""
        if not candidates:
            return []

        candidates.sort(key=lambda c: c.get("score", 0), reverse=True)

        selected = []
        seen_ranges = []
        source_count = 0

        remaining = settings.DAILY_CLIP_TARGET - self._daily_count
        remaining = max(0, remaining)

        for c in candidates:
            if source_count >= settings.MAX_CLIPS_PER_SOURCE:
                break
            if len(selected) >= remaining:
                break

            start, end = c["start_time"], c["end_time"]
            is_overlap = any(not (end <= s or start >= e) for s, e in seen_ranges)
            if is_overlap:
                continue

            selected.append(ClipCandidate(
                id=uuid.uuid4(),
                source_id=source_id,
                transcript_id=None,
                start_time=start,
                end_time=end,
                score=c.get("score", 0),
                hook=c.get("hook"),
                reason=c.get("reason"),
                suggested_title=c.get("suggested_title"),
                status="selected",
                is_duplicate=False,
            ))
            seen_ranges.append((start, end))
            source_count += 1

        await self._save_selected_candidates(selected)
        logger.info("Clips selected", count=len(selected))
        return selected

    async def _run_video_editing(self, source: Source, candidates: List[ClipCandidate]) -> List[Clip]:
        """Process each selected candidate into a final video clip."""
        completed = []

        for candidate in candidates:
            if not self.running:
                break
            try:
                clip = await self._process_single_clip(source, candidate)
                if clip:
                    completed.append(clip)
            except Exception as e:
                logger.error("Clip processing failed", candidate_id=candidate.id, error=str(e))
                await self._save_failed_clip(source.id, candidate, str(e))
                continue

        return completed

    async def _process_single_clip(self, source: Source, candidate: ClipCandidate) -> Optional[Clip]:
        """Process a single clip from candidate to final video."""
        clip_id = uuid.uuid4()
        output_path = str(settings.clips_dir / f"{clip_id}.mp4")

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None,
            self.ffmpeg.process_clip,
            source.file_path,
            candidate.start_time,
            candidate.end_time,
            output_path,
        )

        metadata = self.metadata_gen.generate_metadata(candidate.to_dict(), info)
        self.metadata_gen.save_metadata(metadata, str(clip_id))

        storage_url = self.storage.store_clip(output_path, str(clip_id))

        clip = Clip(
            id=clip_id,
            source_id=source.id,
            candidate_id=candidate.id,
            clip_path=output_path,
            storage_url=storage_url,
            title=metadata["title"],
            caption=metadata["caption"],
            hashtags=metadata["hashtags"],
            duration_seconds=info["duration"],
            resolution=info["resolution"],
            file_size_bytes=info["file_size_bytes"],
            ai_score=candidate.score,
            status="completed",
        )

        await self._save_clip_to_db(clip)
        logger.info("Clip completed", clip_id=str(clip_id), title=metadata["title"])
        return clip

    # --- Database helpers ---

    async def _update_source_status(self, source_id: uuid.UUID, status: str):
        pool = await get_pool()
        await pool.execute(
            "UPDATE sources SET status = $1, updated_at = NOW() WHERE id = $2",
            status, source_id
        )

    async def _create_job(self, source_id: uuid.UUID, job_type: str) -> uuid.UUID:
        job_id = uuid.uuid4()
        pool = await get_pool()
        await pool.execute("""
            INSERT INTO processing_jobs (id, source_id, job_type, status, started_at)
            VALUES ($1, $2, $3, 'running', NOW())
        """, job_id, source_id, job_type)
        return job_id

    async def _complete_job(self, job_id: uuid.UUID):
        pool = await get_pool()
        await pool.execute("""
            UPDATE processing_jobs SET status = 'completed', completed_at = NOW()
            WHERE id = $1
        """, job_id)

    async def _mark_job_failed(self, job_id: uuid.UUID, error: str):
        pool = await get_pool()
        await pool.execute("""
            UPDATE processing_jobs SET status = 'failed', error = $1, completed_at = NOW()
            WHERE id = $1
        """, error, job_id)

    async def _get_existing_transcript(self, source_id: uuid.UUID) -> Optional[Transcript]:
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT * FROM transcripts WHERE source_id = $1 AND status = 'completed'", source_id
        )
        return Transcript.from_db(row) if row else None

    async def _save_transcript_to_db(self, tid: uuid.UUID, source_id: uuid.UUID, result: dict):
        pool = await get_pool()
        await pool.execute("""
            INSERT INTO transcripts (id, source_id, transcript_path, content, language,
                duration_seconds, word_count, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'completed')
        """, tid, source_id, result.get("transcript_path", ""), json.dumps(result["segments"]),
            result["language"], result["duration_seconds"], result["word_count"])

    async def _save_candidates_to_db(self, source_id: uuid.UUID, transcript_id: uuid.UUID, candidates: list):
        pool = await get_pool()
        for c in candidates:
            await pool.execute("""
                INSERT INTO clip_candidates (id, source_id, transcript_id, start_time, end_time,
                    score, hook, reason, suggested_title, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending')
            """, uuid.uuid4(), source_id, transcript_id, c["start_time"], c["end_time"],
                c["score"], c.get("hook"), c.get("reason"), c.get("suggested_title"))

    async def _save_selected_candidates(self, candidates: list):
        pool = await get_pool()
        for c in candidates:
            await pool.execute("""
                INSERT INTO clip_candidates (id, source_id, start_time, end_time, score, hook, reason,
                    suggested_title, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'selected')
                ON CONFLICT DO NOTHING
            """, c.id, c.source_id, c.start_time, c.end_time, c.score, c.hook, c.reason, c.suggested_title)

    async def _save_clip_to_db(self, clip: Clip):
        pool = await get_pool()
        await pool.execute("""
            INSERT INTO clips (id, source_id, candidate_id, clip_path, storage_url, title, caption,
                hashtags, duration_seconds, resolution, file_size_bytes, ai_score, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'completed')
        """, clip.id, clip.source_id, clip.candidate_id, clip.clip_path, clip.storage_url,
            clip.title, clip.caption, json.dumps(clip.hashtags), clip.duration_seconds,
            clip.resolution, clip.file_size_bytes, clip.ai_score)

    async def _save_failed_clip(self, source_id: uuid.UUID, candidate: ClipCandidate, error: str):
        pool = await get_pool()
        await pool.execute("""
            INSERT INTO clips (id, source_id, candidate_id, status, error, retry_count)
            VALUES ($1, $2, $3, 'failed', $4, 1)
        """, uuid.uuid4(), source_id, candidate.id, error)

    async def _update_daily_stats(self, new_clips: int):
        pool = await get_pool()
        today = date.today()
        await pool.execute("""
            INSERT INTO daily_stats (date, clips_generated, clips_target, sources_processed)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (date) DO UPDATE SET
                clips_generated = daily_stats.clips_generated + EXCLUDED.clips_generated,
                sources_processed = daily_stats.sources_processed + 1,
                updated_at = NOW()
        """, today, new_clips, settings.DAILY_CLIP_TARGET)

    async def _check_daily_target(self):
        pool = await get_pool()
        today = date.today()
        row = await pool.fetchrow("SELECT clips_generated FROM daily_stats WHERE date = $1", today)
        if row and row["clips_generated"] >= settings.DAILY_CLIP_TARGET:
            logger.info("Daily target reached", generated=row["clips_generated"], target=settings.DAILY_CLIP_TARGET)
            await asyncio.sleep(60)

    # --- Source Registration ---

    async def register_source(self, name: str, source_type: str, file_path: str = None,
                               url: str = None, campaign_id: str = None,
                               source_key: str = None, is_authorized: bool = True) -> Source:
        if not source_key:
            source_key = f"{source_type}_{uuid.uuid4().hex[:8]}"
        if campaign_id and not validate_campaign_id(campaign_id):
            raise ValueError(f"Invalid campaign ID: {campaign_id}")

        pool = await get_pool()
        source_id = uuid.uuid4()
        await pool.execute("""
            INSERT INTO sources (id, source_key, name, source_type, url, file_path,
                status, is_authorized, campaign_id)
            VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, $8)
        """, source_id, source_key, name, source_type, url, file_path, is_authorized, campaign_id)

        logger.info("Source registered", source_key=source_key, name=name)
        return Source(
            id=source_id, source_key=source_key, name=name, source_type=source_type,
            url=url, file_path=file_path, status="pending",
            is_authorized=is_authorized, campaign_id=campaign_id,
        )

    async def discover_sources(self):
        """Auto-discover source videos from the sources folder."""
        sources_dir = Path(settings.SOURCES_FOLDER)
        if not sources_dir.exists():
            logger.info("Sources directory does not exist", path=str(sources_dir))
            return

        valid_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
        for f in sources_dir.iterdir():
            if f.suffix.lower() in valid_extensions:
                pool = await get_pool()
                existing = await pool.fetchrow("SELECT id FROM sources WHERE file_path = $1", str(f))
                if not existing:
                    await self.register_source(
                        name=f.stem, source_type="file", file_path=str(f),
                        campaign_id="ForgeGUI Clipping [Roblox]", is_authorized=True,
                    )
                    logger.info("Discovered source", file=str(f))

        url_file = Path(settings.SOURCE_URLS_FILE)
        if url_file.exists():
            for line in url_file.read_text().strip().split("\n"):
                line = line.strip()
                if line and line.startswith(("http://", "https://")):
                    pool = await get_pool()
                    existing = await pool.fetchrow("SELECT id FROM sources WHERE url = $1", line)
                    if not existing:
                        await self.register_source(
                            name=Path(line).stem, source_type="url", url=line,
                            campaign_id="ForgeGUI Clipping [Roblox]", is_authorized=True,
                        )
                        logger.info("Discovered URL source", url=line)
