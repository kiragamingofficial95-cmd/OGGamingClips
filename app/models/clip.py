"""Clip and candidate models."""
from dataclasses import dataclass, field
from typing import Optional, List
import uuid
from datetime import datetime


@dataclass
class ClipCandidate:
    id: uuid.UUID
    source_id: uuid.UUID
    transcript_id: Optional[uuid.UUID] = None
    start_time: float = 0
    end_time: float = 0
    score: float = 0
    hook: Optional[str] = None
    reason: Optional[str] = None
    suggested_title: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    status: str = "pending"
    is_duplicate: bool = False
    created_at: Optional[datetime] = None

    @classmethod
    def from_db(cls, row) -> "ClipCandidate":
        return cls(
            id=row["id"],
            source_id=row["source_id"],
            transcript_id=row.get("transcript_id"),
            start_time=row.get("start_time", 0),
            end_time=row.get("end_time", 0),
            score=row.get("score", 0),
            hook=row.get("hook"),
            reason=row.get("reason"),
            suggested_title=row.get("suggested_title"),
            metadata=row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {},
            status=row.get("status", "pending"),
            is_duplicate=row.get("is_duplicate", False),
            created_at=row.get("created_at"),
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "source_id": str(self.source_id),
            "transcript_id": str(self.transcript_id) if self.transcript_id else None,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "score": self.score,
            "hook": self.hook,
            "reason": self.reason,
            "suggested_title": self.suggested_title,
            "metadata": self.metadata,
            "status": self.status,
            "is_duplicate": self.is_duplicate,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class Clip:
    id: uuid.UUID
    source_id: uuid.UUID
    candidate_id: Optional[uuid.UUID] = None
    clip_path: Optional[str] = None
    storage_url: Optional[str] = None
    title: Optional[str] = None
    caption: Optional[str] = None
    hashtags: List[str] = field(default_factory=list)
    duration_seconds: Optional[float] = None
    resolution: Optional[str] = None
    file_size_bytes: Optional[int] = None
    ai_score: Optional[float] = None
    status: str = "pending"
    error: Optional[str] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_db(cls, row) -> "Clip":
        return cls(
            id=row["id"],
            source_id=row["source_id"],
            candidate_id=row.get("candidate_id"),
            clip_path=row.get("clip_path"),
            storage_url=row.get("storage_url"),
            title=row.get("title"),
            caption=row.get("caption"),
            hashtags=row.get("hashtags", []) if row.get("hashtags") else [],
            duration_seconds=row.get("duration_seconds"),
            resolution=row.get("resolution"),
            file_size_bytes=row.get("file_size_bytes"),
            ai_score=row.get("ai_score"),
            status=row.get("status", "pending"),
            error=row.get("error"),
            retry_count=row.get("retry_count", 0),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "source_id": str(self.source_id),
            "candidate_id": str(self.candidate_id) if self.candidate_id else None,
            "clip_path": self.clip_path,
            "storage_url": self.storage_url,
            "title": self.title,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "duration_seconds": self.duration_seconds,
            "resolution": self.resolution,
            "file_size_bytes": self.file_size_bytes,
            "ai_score": self.ai_score,
            "status": self.status,
            "error": self.error,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
