"""Input validation utilities."""
import os
import re
from pathlib import Path
from typing import Optional


def validate_source_path(path: str) -> bool:
    """Validate that a source file path exists and has a valid video extension."""
    valid_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    p = Path(path)
    if not p.exists():
        return False
    if p.suffix.lower() not in valid_extensions:
        return False
    return True


def validate_url(url: str) -> bool:
    """Basic URL validation."""
    return url.startswith("http://") or url.startswith("https://")


def validate_clip_timestamps(start: float, end: float, min_dur: float = 5, max_dur: float = 300) -> bool:
    """Validate clip start/end times."""
    if start < 0 or end <= start:
        return False
    duration = end - start
    if duration <= min_dur or duration > max_dur:
        return False
    return True


def sanitize_title(title: str) -> str:
    """Sanitize a title for file naming."""
    invalid_chars = '<>:"/\\|?*\n\r\t '
    for c in invalid_chars:
        title = title.replace(c, '_')
    # Remove other unsafe characters
    title = re.sub(r'[^\w\s_-]', '', title)
    return title.strip()[:100]


def validate_campaign_id(campaign_id: str) -> bool:
    """Validate campaign ID format."""
    if not campaign_id or not isinstance(campaign_id, str):
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', campaign_id))
