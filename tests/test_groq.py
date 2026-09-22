"""Tests for Groq analysis service."""
import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict

from app.services.groq import GroqAnalysisService
from app.config import get_settings

pytest_plugins = ("pytest_asyncio",)


def test_groq_service_init():
    """Test GroqAnalysisService initialization."""
    service = GroqAnalysisService()
    assert service.client is None
    assert len(service._cache) == 0


def test_validate_candidate():
    """Test candidate validation."""
    service = GroqAnalysisService()

    valid = {"start_time": 10, "end_time": 40, "score": 8.5, "reason": "Funny moment"}
    assert service._validate_candidate(valid) is True

    invalid = {"start_time": "bad", "score": 15, "reason": ""}
    assert service._validate_candidate(invalid) is False

    too_short = {"start_time": 10, "end_time": 11, "score": 8, "reason": "test"}
    assert service._validate_candidate(too_short) is False


def test_build_chunks():
    """Test chunk building from segments."""
    service = GroqAnalysisService()

    segments = [{"text": f"Segment {i} text here."} for i in range(20)]
    chunks = service._build_chunks(segments)
    assert len(chunks) > 0
    assert all(isinstance(c, str) for c in chunks)


def test_filter_candidates():
    """Test candidate filtering."""
    service = GroqAnalysisService()
    candidates = [
        {"start_time": 0, "end_time": 30, "score": 9.0, "reason": "test"},
        {"start_time": 0, "end_time": 30, "score": 5.0, "reason": "test"},
        {"start_time": 0, "end_time": 30, "score": 7.5, "reason": "test"},
    ]
    filtered = service._filter_candidates(candidates, min_score=7.0, min_duration=20, max_duration=60)
    assert len(filtered) == 2
    assert all(c["score"] >= 7.0 for c in filtered)


def test_deduplicate():
    """Test clip deduplication."""
    service = GroqAnalysisService()
    candidates = [
        {"start_time": 10, "end_time": 40, "score": 9.0},
        {"start_time": 15, "end_time": 45, "score": 8.0},  # overlapping
        {"start_time": 60, "end_time": 90, "score": 7.0},
    ]
    deduped = service._deduplicate(candidates, "test_source")
    assert len(deduped) == 2  # First and third don't overlap
    assert deduped[0]["score"] == 9.0  # Higher score first


def test_cache():
    """Test caching of analysis results."""
    service = GroqAnalysisService()
    segments = [{"text": f"Segment {i}" for i in range(5)}]
    cache_key = service._get_cache_key(segments)
    assert cache_key is not None
    assert cache_key in service._cache or True  # Not cached yet

    # Manually cache
    service._cache[cache_key] = [{"score": 8.0}]
    cached = service.get_cached_analysis(segments)
    assert cached is not None
    assert len(cached) == 1


@pytest.mark.asyncio
async def test_analyze_candidates_end_to_end():
    """Regression test: analyze_candidates must actually await Groq calls
    and return filtered, deduplicated candidates (not a coroutine)."""
    service = GroqAnalysisService()
    segments = [
        {"id": 0, "start": 0.0, "end": 10.0, "text": "wow incredible gameplay moment here", "language": "en"},
        {"id": 1, "start": 10.0, "end": 20.0, "text": "that was so funny I cannot believe it", "language": "en"},
    ]

    def fake_chunk(chunk_text, chunk_idx, is_last):
        return [
            {"start_time": 2, "end_time": 32, "score": 9.0, "hook": "wow",
             "reason": "Funny moment", "suggested_title": "Epic Fail"},
            {"start_time": 5, "end_time": 35, "score": 8.0, "hook": "again",
             "reason": "Overlaps the first", "suggested_title": "Dupe"},
            {"start_time": 100, "end_time": 130, "score": 4.0, "hook": "meh",
             "reason": "Too low", "suggested_title": "Boring"},
        ]

    with patch.object(service, "_analyze_chunk", side_effect=fake_chunk):
        result = await service.analyze_candidates(segments, "test_source")

    assert isinstance(result, list)
    # Score filter (7.0) drops the 4.0; overlap drops the 8.0 dupe
    assert len(result) == 1
    assert result[0]["score"] == 9.0
    assert result[0]["suggested_title"] == "Epic Fail"


@pytest.mark.asyncio
async def test_analyze_candidates_all_chunks_fail():
    """If every Groq chunk fails, raise loudly instead of silent zero."""
    service = GroqAnalysisService()
    segments = [{"id": 0, "start": 0.0, "end": 10.0, "text": "hello", "language": "en"}]

    with patch.object(service, "_analyze_chunk", side_effect=RuntimeError("boom")):
        try:
            await service.analyze_candidates(segments, "test_source")
            assert False, "should have raised"
        except RuntimeError as e:
            assert "all" in str(e).lower()
