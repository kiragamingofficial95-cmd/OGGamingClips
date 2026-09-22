"""Groq Whisper API transcription service.

Uses Groq's hosted Whisper API (free tier) instead of local torch/whisper,
so the Railway image stays small. Long videos are split into audio chunks
to stay under Groq's per-request file size limit.
"""
import asyncio
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from app.config import get_settings
from app.utils.logger import get_logger
from app.utils.validators import validate_source_path

logger = get_logger("groq-whisper")

TRANSCRIBE_MODEL = "whisper-large-v3-turbo"
CHUNK_SECONDS = 600  # 10-minute audio chunks
MAX_FILE_MB = 24  # Groq rejects files >= 25 MB


class GroqTranscriptionService:
    def __init__(self):
        self.settings = get_settings()
        self._client = None

    def _get_client(self):
        """Get or create Groq client (lazy so import never fails)."""
        if self._client is None:
            from groq import Groq
            if not self.settings.GROQ_API_KEY:
                raise ValueError("GROQ_API_KEY is not set")
            self._client = Groq(api_key=self.settings.GROQ_API_KEY)
        return self._client

    async def transcribe(self, source_path: str, source_id: str = None) -> Dict:
        """Transcribe a video file via Groq Whisper API.

        Returns the same dict shape as the local Whisper service:
        segments with start/end/text plus duration, word count, and
        transcript file path.
        """
        if not validate_source_path(source_path):
            raise ValueError(f"Invalid source path: {source_path}")

        logger.info("Starting Groq transcription", source_path=source_path)

        duration = self._probe_duration(source_path)
        chunks = self._plan_chunks(duration)

        all_segments: List[Dict] = []
        language = "en"

        for idx, (offset, length) in enumerate(chunks):
            audio_path = self._extract_audio_chunk(source_path, offset, length, idx)
            try:
                result = await asyncio.to_thread(self._transcribe_chunk, audio_path)
                language = result.get("language") or language
                for seg in result.get("segments", []):
                    all_segments.append({
                        "id": len(all_segments),
                        "start": round(offset + float(seg["start"]), 3),
                        "end": round(offset + float(seg["end"]), 3),
                        "text": str(seg["text"]).strip(),
                        "language": language,
                        "temperature": 0,
                    })
                logger.info("Chunk transcribed", chunk=idx + 1, total=len(chunks),
                            segments=len(result.get("segments", [])))
            finally:
                try:
                    Path(audio_path).unlink(missing_ok=True)
                except OSError:
                    pass

        output_path = self._save_transcript(all_segments, source_path, source_id)

        transcript_data = {
            "source_id": source_id,
            "segments": all_segments,
            "language": language,
            "duration_seconds": round(duration or (all_segments[-1]["end"] if all_segments else 0), 2),
            "word_count": sum(len(s["text"].split()) for s in all_segments),
            "status": "completed",
            "transcript_path": output_path,
        }

        logger.info("Groq transcription complete", segments=len(all_segments),
                    duration=transcript_data["duration_seconds"])
        return transcript_data

    def _transcribe_chunk(self, audio_path: str) -> Dict:
        """Send one audio chunk to Groq (blocking, run in a thread)."""
        client = self._get_client()
        with open(audio_path, "rb") as f:
            response = client.audio.transcriptions.create(
                file=(Path(audio_path).name, f.read()),
                model=TRANSCRIBE_MODEL,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        segments = []
        for seg in getattr(response, "segments", []) or []:
            if isinstance(seg, dict):
                segments.append({"start": seg["start"], "end": seg["end"], "text": seg["text"]})
            else:
                segments.append({"start": seg.start, "end": seg.end, "text": seg.text})
        return {
            "segments": segments,
            "language": getattr(response, "language", "en") or "en",
        }

    def _probe_duration(self, source_path: str) -> Optional[float]:
        """Get media duration in seconds via ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", source_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return None
            duration = json.loads(result.stdout).get("format", {}).get("duration")
            return float(duration) if duration else None
        except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def _plan_chunks(self, duration: Optional[float]) -> List[tuple]:
        """Split duration into (offset, length) chunks."""
        if not duration or duration <= 0:
            return [(0, CHUNK_SECONDS)]
        chunks = []
        offset = 0.0
        while offset < duration:
            chunks.append((offset, min(CHUNK_SECONDS, duration - offset)))
            offset += CHUNK_SECONDS
        return chunks

    def _extract_audio_chunk(self, source_path: str, offset: float, length: float, idx: int) -> str:
        """Extract a compressed mono audio chunk with FFmpeg."""
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=f"_chunk{idx}.mp3", delete=False)
        tmp.close()
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(offset),
            "-i", source_path,
            "-t", str(length),
            "-vn", "-ar", "16000", "-ac", "1",
            "-c:a", "libmp3lame", "-b:a", "64k",
            tmp.name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg audio extract failed: {result.stderr[-500:]}")
        size_mb = Path(tmp.name).stat().st_size / (1024 * 1024)
        if size_mb >= MAX_FILE_MB:
            raise RuntimeError(
                f"Audio chunk too large for Groq API ({size_mb:.1f} MB). "
                "Shorten CHUNK_SECONDS."
            )
        return tmp.name

    def _save_transcript(self, segments: List[Dict], source_path: str, source_id: str = None) -> str:
        """Save transcript segments as JSON file."""
        output_dir = self.settings.transcripts_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        name = Path(source_path).stem
        suffix = f"_{source_id}" if source_id else ""
        output_path = output_dir / f"{name}{suffix}_transcript.json"

        with open(output_path, "w") as f:
            json.dump(segments, f, indent=2)

        return str(output_path)
