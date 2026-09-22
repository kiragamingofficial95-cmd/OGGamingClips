"""Transcript model."""
from dataclasses import dataclass, field
from typing import Optional, List
import uuid
from datetime import datetime


@dataclass
class Transcript:
    id: uuid.UUID
    source_id: uuid.UUID
    transcript_path: Optional[str] = None
    content: List[dict] = field(default_factory=list)
    language: str = "en"
    duration_seconds: Optional[float] = None
    word_count: Optional[int] = None
    status: str = "pending"
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_db(cls, row) -> "Transcript":
        content = row.get("content", [])
        if isinstance(content, str):
            import json
            content = json.loads(content)
        return cls(
            id=row["id"],
            source_id=row["source_id"],
            transcript_path=row.get("transcript_path"),
            content=content,
            language=row.get("language", "en"),
            duration_seconds=row.get("duration_seconds"),
            word_count=row.get("word_count"),
            status=row.get("status", "pending"),
            error=row.get("error"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "source_id": str(self.source_id),
            "transcript_path": self.transcript_path,
            "content": self.content,
            "language": self.language,
            "duration_seconds": self.duration_seconds,
            "word_count": self.word_count,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
