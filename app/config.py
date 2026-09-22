"""Centralized configuration from environment variables."""
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from pathlib import Path


class Settings(BaseSettings):
    # --- Core ---
    DAILY_CLIP_TARGET: int = Field(default=10, ge=1, le=50)
    MIN_CLIP_SCORE: float = Field(default=7.0, ge=0.0, le=10.0)
    MIN_CLIP_DURATION: int = Field(default=20, ge=5)
    MAX_CLIP_DURATION: int = Field(default=60, ge=10)
    MAX_CLIPS_PER_SOURCE: int = Field(default=5, ge=1, le=20)

    # --- Groq ---
    GROQ_API_KEY: str = Field(default="")
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile")
    GROQ_CHUNK_SIZE: int = Field(default=5000, ge=100)
    GROQ_OVERLAP: int = Field(default=500, ge=0)

    # --- Whisper ---
    WHISPER_MODEL: str = Field(default="medium")
    WHISPER_DEVICE: str = Field(default="cpu")

    # --- Database ---
    DATABASE_URL: str = Field(default="postgresql://user:password@localhost:5432/oggamingclips")
    DATABASE_POOL_MIN: int = Field(default=2, ge=1)
    DATABASE_POOL_MAX: int = Field(default=10, ge=1, le=50)

    # --- Redis ---
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_MAX_CONNECTIONS: int = Field(default=10, ge=1)

    # --- Storage ---
    STORAGE_PROVIDER: str = Field(default="local")
    STORAGE_BASE_PATH: str = Field(default="/data/clips")
    STORAGE_ENDPOINT: str = Field(default="")
    STORAGE_ACCESS_KEY: str = Field(default="")
    STORAGE_SECRET_KEY: str = Field(default="")
    STORAGE_BUCKET: str = Field(default="oggamingclips")

    # --- Worker ---
    WORKER_POLL_INTERVAL: int = Field(default=30, ge=5)
    WORKER_MAX_RETRIES: int = Field(default=3, ge=0, le=10)
    WORKER_RETRY_BACKOFF: float = Field(default=2.0, ge=1.0)
    WORKER_MAX_CONCURRENT: int = Field(default=2, ge=1, le=10)
    HEALTH_CHECK_PORT: int = Field(default=8000, ge=1)

    # --- Input Sources ---
    SOURCES_FOLDER: str = Field(default="/data/sources")
    SOURCE_URLS_FILE: str = Field(default="/data/source_urls.txt")

    # --- Logging ---
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v):
        if not v or v == "":
            raise ValueError("DATABASE_URL is required")
        return v

    @property
    def storage_path(self) -> Path:
        base = Path(self.STORAGE_BASE_PATH)
        return base

    @property
    def sources_dir(self) -> Path:
        return Path(self.SOURCES_FOLDER)

    @property
    def clips_dir(self) -> Path:
        return Path(self.STORAGE_BASE_PATH) / "clips"

    @property
    def transcripts_dir(self) -> Path:
        return Path(self.STORAGE_BASE_PATH) / "transcripts"

    @property
    def candidates_dir(self) -> Path:
        return Path(self.STORAGE_BASE_PATH) / "candidates"

    @property
    def metadata_dir(self) -> Path:
        return Path(self.STORAGE_BASE_PATH) / "metadata"

    @property
    def failed_dir(self) -> Path:
        return Path(self.STORAGE_BASE_PATH) / "failed"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
