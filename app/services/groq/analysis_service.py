"""Groq AI analysis service for clip candidate detection."""
import json
import asyncio
from typing import Optional, List, Dict
from app.config import get_settings
from app.utils.logger import get_logger
from app.utils.retry import retry_with_backoff

logger = get_logger("groq")


class GroqAnalysisService:
    def __init__(self):
        self.settings = get_settings()
        self.client = None
        self._cache: Dict[str, List[Dict]] = {}  # cache by transcript content hash

    def _get_client(self):
        """Get or create Groq client."""
        if self.client is None:
            import groq
            if not self.settings.GROQ_API_KEY:
                raise ValueError("GROQ_API_KEY is not set")
            self.client = groq.Groq(api_key=self.settings.GROQ_API_KEY)
        return self.client

    def _get_cache_key(self, content: list) -> str:
        """Create a cache key from transcript segments."""
        text_snippet = " ".join(s.get("text", "") for s in content[:10])
        return str(hash(text_snippet))

    async def analyze_candidates(
        self,
        segments: List[Dict],
        source_id: str,
        min_score: float = None,
        min_duration: int = None,
        max_duration: int = None,
    ) -> List[Dict]:
        """
        Analyze transcript segments for clip candidates using Groq.
        Returns list of candidate clip dicts.
        """
        if min_score is None:
            min_score = self.settings.MIN_CLIP_SCORE
        if min_duration is None:
            min_duration = self.settings.MIN_CLIP_DURATION
        if max_duration is None:
            max_duration = self.settings.MAX_CLIP_DURATION

        # Check cache
        cache_key = self._get_cache_key(segments)
        if cache_key in self._cache:
            logger.info("Using cached analysis", source_id=source_id)
            cached = self._cache[cache_key]
            return [c for c in cached if c.get("score", 0) >= min_score]

        # Build chunks from segments
        chunks = self._build_chunks(segments)
        if not chunks:
            return []

        all_candidates = []
        chunks_succeeded = 0

        for chunk_idx, chunk in enumerate(chunks):
            is_last = chunk_idx == len(chunks) - 1
            try:
                candidates = await retry_with_backoff(
                    lambda c=chunk, i=chunk_idx, last=is_last: asyncio.to_thread(
                        self._analyze_chunk, c, i, last
                    ),
                    max_retries=self.settings.WORKER_MAX_RETRIES,
                    base_delay=self.settings.WORKER_RETRY_BACKOFF,
                    retry_exceptions=(Exception,),
                )
                all_candidates.extend(candidates)
                chunks_succeeded += 1
            except Exception as e:
                logger.error("Failed to analyze chunk", chunk=chunk_idx, error=str(e))
                continue

        if chunks_succeeded == 0:
            raise RuntimeError(
                "Groq analysis failed for all %d chunk(s); check GROQ_API_KEY and rate limits" % len(chunks)
            )

        # Filter and deduplicate
        filtered = self._filter_candidates(all_candidates, min_score, min_duration, max_duration)
        deduplicated = self._deduplicate(filtered, source_id)

        # Cache results
        self._cache[cache_key] = deduplicated

        logger.info("Analysis complete", source_id=source_id, candidates=len(deduplicated))
        return deduplicated

    def _analyze_chunk(self, chunk_text: str, chunk_idx: int, is_last: bool) -> List[Dict]:
        """Send a chunk to Groq for clip candidate analysis (blocking; call in a thread)."""
        client = self._get_client()

        prompt = f"""Analyze the following transcript chunk and identify potential short-form clip moments for gaming content on Instagram.

For EACH clip moment you identify, return a JSON array with these fields:
- start_time: number (seconds from start of video)
- end_time: number (seconds, must be start_time + 20 to 60)
- score: number (0-10, rate the clip potential)
- hook: string (the first line that would hook a viewer)
- reason: string (why this is a good clip)
- suggested_title: string (title for the clip)

CRITERIA FOR GOOD CLIPS:
- Strong hook in first 3 seconds
- Funny, interesting, surprising, or exciting moments
- Clear standalone context (don't need prior knowledge)
- 20-60 seconds duration ideally
- Roblox gameplay highlights, strong reactions, funny moments
- Educational or useful content

AVOID:
- Clips requiring excessive context
- Dead or boring sections
- Nearly duplicate moments
- Promotional content

TRANSCRIPT CHUNK (part {chunk_idx + 1}{', last part' if is_last else ''}):
{chunk_text}

Return ONLY a valid JSON array. Do not wrap in markdown code blocks."""

        try:
            response = client.chat.completions.create(
                model=self.settings.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=4096,
            )

            content = response.choices[0].message.content
            candidates = json.loads(content.strip())

            if not isinstance(candidates, list):
                candidates = [candidates]

            # Validate each candidate
            valid = []
            for c in candidates:
                if self._validate_candidate(c):
                    c["source_id"] = chunk_idx
                    valid.append(c)

            return valid

        except json.JSONDecodeError as e:
            logger.error("Groq returned invalid JSON", chunk=chunk_idx, error=str(e))
            return []
        except Exception as e:
            logger.error("Groq API error", chunk=chunk_idx, error=str(e))
            raise

    def _validate_candidate(self, c: Dict) -> bool:
        """Validate a single clip candidate."""
        try:
            if not isinstance(c.get("start_time"), (int, float)):
                return False
            if not isinstance(c.get("end_time"), (int, float)):
                return False
            if not isinstance(c.get("score"), (int, float)):
                return False
            if c["end_time"] - c["start_time"] < 5:
                return False
            if c["score"] < 0 or c["score"] > 10:
                return False
            if not c.get("reason"):
                return False
            return True
        except Exception:
            return False

    def _build_chunks(self, segments: List[Dict]) -> List[str]:
        """Build text chunks from segments for Groq analysis."""
        if not segments:
            return []

        chunk_size = self.settings.GROQ_CHUNK_SIZE
        overlap = self.settings.GROQ_OVERLAP
        chunks = []
        current_chunk = []
        current_size = 0

        for seg in segments:
            seg_text = seg["text"]
            seg_size = len(seg_text)

            if current_size + seg_size > chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                # Keep overlap text from the end
                overlap_text = " ".join(current_chunk[-(max(1, int(overlap/50))):])
                current_chunk = overlap_text.split() if overlap_text else []
                current_size = sum(len(t) for t in current_chunk)

            current_chunk.append(seg_text)
            current_size += seg_size

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks if chunks else [" ".join(s["text"] for s in segments)]

    def _filter_candidates(
        self,
        candidates: List[Dict],
        min_score: float,
        min_duration: int,
        max_duration: int,
    ) -> List[Dict]:
        """Filter candidates by score and duration."""
        filtered = []
        for c in candidates:
            dur = c["end_time"] - c["start_time"]
            if c.get("score", 0) >= min_score and min_duration <= dur <= max_duration:
                filtered.append(c)
        return filtered

    def _deduplicate(self, candidates: List[Dict], source_id: str) -> List[Dict]:
        """Remove duplicate/overlapping clips."""
        # Sort by score descending
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

        deduped = []
        seen_ranges = []

        for c in candidates:
            start, end = c["start_time"], c["end_time"]
            is_overlap = False
            for s, e in seen_ranges:
                if not (end <= s or start >= e):  # overlap detected
                    is_overlap = True
                    break

            if not is_overlap:
                deduped.append(c)
                seen_ranges.append((start, end))

        return deduped

    def get_cached_analysis(self, content: list) -> Optional[List[Dict]]:
        """Get cached analysis if available."""
        key = self._get_cache_key(content)
        return self._cache.get(key)
