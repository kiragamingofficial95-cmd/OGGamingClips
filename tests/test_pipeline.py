"""Tests for the pipeline worker."""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import uuid
from datetime import date

from app.workers.pipeline_worker import PipelineWorker
from app.config import get_settings
from app.models.source import Source

pytest_plugins = ("pytest_asyncio",)


def test_worker_init():
    """Test PipelineWorker initialization."""
    worker = PipelineWorker()
    assert worker.running is False
    assert worker._daily_count == 0
    assert worker._today == date.today().isoformat()
    assert worker.ffmpeg is not None
    assert worker.groq is not None
    assert worker.storage is not None


@pytest.mark.asyncio
@patch('app.workers.pipeline_worker.get_pool')
async def test_select_clips_basic(mock_get_pool):
    """Test basic clip selection logic."""
    mock_pool = AsyncMock()
    mock_get_pool.return_value = mock_pool
    mock_pool.fetchval.return_value = 0

    worker = PipelineWorker()
    candidates = [
        {"start_time": 10, "end_time": 40, "score": 9.0, "hook": "Hook 1", "reason": "Funny", "suggested_title": "Title 1"},
        {"start_time": 15, "end_time": 45, "score": 8.0, "hook": "Hook 2", "reason": "Cool", "suggested_title": "Title 2"},
        {"start_time": 60, "end_time": 90, "score": 7.5, "hook": "Hook 3", "reason": "Nice", "suggested_title": "Title 3"},
    ]
    source_id = uuid.uuid4()
    selected = await worker._select_clips(candidates, source_id)
    assert len(selected) > 0
    assert all(isinstance(s.score, float) for s in selected)
    for i in range(len(selected) - 1):
        assert selected[i].end_time <= selected[i+1].start_time


def test_validate_clip_timestamps():
    """Test timestamp validation."""
    from app.utils.validators import validate_clip_timestamps
    assert validate_clip_timestamps(10, 40) is True
    assert validate_clip_timestamps(0, 5) is False  # Too short (5 <= 5)
    assert validate_clip_timestamps(-1, 10) is False  # Negative start
    assert validate_clip_timestamps(10, 5) is False  # End before start
    assert validate_clip_timestamps(10, 200) is True  # Within max
    assert validate_clip_timestamps(10, 300) is True  # Exactly max
    assert validate_clip_timestamps(10, 350) is False  # Over max duration


def test_sanitize_title():
    """Test title sanitization."""
    from app.utils.validators import sanitize_title
    assert sanitize_title("Hello World!") == "Hello_World"
    assert "_" in sanitize_title("Test/Path:Name")
    assert len(sanitize_title("a" * 200)) <= 100  # Max length


def test_source_model():
    """Test Source model."""
    source_id = uuid.uuid4()
    source = Source(
        id=source_id, source_key="test_001", name="Test Video",
    )
    d = source.to_dict()
    assert d["source_key"] == "test_001"
    assert d["id"] == str(source_id)
    assert d["status"] == "pending"
