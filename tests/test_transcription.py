"""Tests for transcription service."""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from app.services.transcription import WhisperService
from app.config import get_settings


def test_whisper_service_init():
    """Test WhisperService initialization."""
    service = WhisperService()
    assert service.settings is not None
    assert service._model is None


def test_transcript_structure():
    """Test transcript data structure."""
    segments = [
        {
            "id": 0,
            "start": 0.0,
            "end": 5.5,
            "text": "Welcome to the gaming clip",
            "language": "en",
            "temperature": 0.0,
        }
    ]
    assert len(segments) == 1
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 5.5
    assert "text" in segments[0]


def test_save_transcript_creates_file(tmp_path):
    """Test that transcript saving works."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        settings = get_settings()
        settings.STORAGE_BASE_PATH = tmp
        service = WhisperService()

        segments = [{"id": 0, "start": 0.0, "end": 5.0, "text": "test"}]
        path = service._save_transcript(segments, "/fake/video.mp4")
        assert Path(path).exists()

        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["text"] == "test"
