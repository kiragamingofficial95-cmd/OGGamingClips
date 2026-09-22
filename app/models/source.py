"""Source model."""
from dataclasses import dataclass, field
from typing import Optional
import uuid
from datetime import datetime


@dataclass
class Source:
    id: uuid.UUID
    source_key: str
    name: str
    source_type: str = "file"
    url: Optional[str] = None
    file_path: Optional[str] = None
    status: str = "pending"
    is_authorized: bool = True
    campaign_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_db(cls, row) -> "Source":
        return cls(
            id=row["id"],
            source_key=row["source_key"],
            name=row["name"],
            source_type=row.get("source_type", "file"),
            url=row.get("url"),
            file_path=row.get("file_path"),
            status=row.get("status", "pending"),
            is_authorized=row.get("is_authorized", True),
            campaign_id=row.get("campaign_id"),
            metadata=row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {},
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "source_key": self.source_key,
            "name": self.name,
            "source_type": self.source_type,
            "url": self.url,
            "file_path": self.file_path,
            "status": self.status,
            "is_authorized": self.is_authorized,
            "campaign_id": self.campaign_id,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
