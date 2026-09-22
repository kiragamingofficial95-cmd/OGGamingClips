"""Test configuration."""
import pytest
from app.config import get_settings


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def sample_segments():
    return [
        {"id": i, "start": float(i * 10), "end": float(i * 10 + 10), "text": f"Segment {i} text content for testing.", "language": "en"}
        for i in range(10)
    ]
