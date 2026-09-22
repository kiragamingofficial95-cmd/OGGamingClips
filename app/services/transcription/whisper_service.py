"""Whisper-based transcription service with timestamps."""
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Optional, List, Dict

from app.config import get_settings
from app.utils.logger import get_logger
from app.utils.validators import validate_source_path

logger = get_logger("whisper")


class WhisperService:
    def __init__(self):
        self.settings = get_settings()
        self._model = None

    def _get_model(self):
        import whisper
        if self._model is None:
            logger.info("Loading Whisper model", model=self.settings.WHISPER_MODEL)
            self._model = whisper.load_model(self.settings.WHISPER_MODEL, device=self.settings.WHISPER_DEVICE)
            logger.info("Whisper model loaded")
        return self._model
        return self._model

    async def transcribe(self, source_path: str, source_id: str = None) -> Dict:
        """Transcribe a video file and return timestamped segments."""
        if not validate_source_path(source_path):
            raise ValueError(f"Invalid source path: {source_path}")

        logger.info("Starting transcription", source_path=source_path)

        loop = asyncio.get_event_loop()
        model = self._get_model()

        # Run blocking whisper in thread
        result = await loop.run_in_executor(
            None,
            model.transcribe,
            source_path,
            self.settings.WHISPER_MODEL,
        )

        # Build timestamped segments
        segments = []
        for segment in result["segments"]:
            segments.append({
                "id": segment["id"],
                "start": round(segment["start"], 3),
                "end": round(segment["end"], 3),
                "text": segment["text"].strip(),
                "language": segment.get("language", "en"),
                "temperature": segment.get("temperature", 0),
            })

        # Save transcript to file
        output_path = self._save_transcript(segments, source_path, source_id)

        transcript_data = {
            "source_id": source_id,
            "segments": segments,
            "language": result.get("language", "en"),
            "duration_seconds": round(result.get("duration", 0), 2),
            "word_count": sum(len(s["text"].split()) for s in segments),
            "status": "completed",
            "transcript_path": output_path,
        }

        logger.info("Transcription complete", segments=len(segments), duration=transcript_data["duration_seconds"])
        return transcript_data

    def _save_transcript(self, segments: List[Dict], source_path: str, source_id: str = None) -> str:
        """Save transcript as JSON file."""
        output_dir = self.settings.transcripts_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        name = Path(source_path).stem
        suffix = f"_{source_id}" if source_id else ""
        output_path = output_dir / f"{name}{suffix}_transcript.json"

        with open(output_path, 'w') as f:
            json.dump(segments, f, indent=2)

        return str(output_path)

    async def transcribe_from_path_async(self, source_path: str) -> Dict:
        """Async wrapper for transcribe."""
        return await self.transcribe(source_path)
