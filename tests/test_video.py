"""Tests for video editing service."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import os

from app.services.video import FFmpegService
from app.config import get_settings


def test_ffmpeg_service_init():
    """Test FFmpegService initialization."""
    service = FFmpegService()
    assert service.settings is not None


def test_video_info_with_mock():
    """Test video info extraction with mock."""
    service = FFmpegService()

    # Mock ffprobe not found case
    with patch('app.services.video.ffmpeg_service.shutil') as mock_shutil:
        mock_shutil.which.return_value = None
        info = service._get_video_info("/nonexistent/path/video.mp4")
        assert info["exists"] is False
        assert info.get("error") == "ffprobe not found"


def test_video_info_nonexistent():
    """Test video info for nonexistent file."""
    service = FFmpegService()

    # Mock ffprobe not found case
    with patch('app.services.video.ffmpeg_service.shutil') as mock_shutil:
        mock_shutil.which.return_value = None
        info = service._get_video_info("/nonexistent/path/video.mp4")
        assert info["exists"] is False
