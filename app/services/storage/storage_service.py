"""Storage service for local and S3-compatible backends."""
import os
import json
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger("storage")


class StorageProvider(ABC):
    @abstractmethod
    def upload(self, local_path: str, remote_path: str) -> str:
        """Upload file and return public URL."""
        pass

    @abstractmethod
    def download(self, remote_path: str, local_path: str):
        """Download file from remote."""
        pass

    @abstractmethod
    def delete(self, remote_path: str):
        """Delete remote file."""
        pass

    @abstractmethod
    def exists(self, remote_path: str) -> bool:
        """Check if file exists."""
        pass


class LocalStorage(StorageProvider):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path: str, remote_path: str) -> str:
        dest = self.base_path / remote_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.link(local_path, dest) if os.path.exists(local_path) else None
        # Copy instead of link for reliability
        import shutil
        shutil.copy2(local_path, dest)
        logger.info("Uploaded to local storage", path=str(dest))
        return str(dest)

    def download(self, remote_path: str, local_path: str):
        src = self.base_path / remote_path
        import shutil
        shutil.copy2(src, local_path)

    def delete(self, remote_path: str):
        path = self.base_path / remote_path
        if path.exists():
            path.unlink()

    def exists(self, remote_path: str) -> bool:
        return (self.base_path / remote_path).exists()


class S3Storage(StorageProvider):
    def __init__(self, endpoint, access_key, secret_key, bucket):
        import boto3
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self.bucket = bucket

    def upload(self, local_path: str, remote_path: str) -> str:
        self.s3.upload_file(local_path, self.bucket, remote_path)
        url = f"{self.s3._endpoint_url}/{self.bucket}/{remote_path}"
        logger.info("Uploaded to S3", url=url)
        return url

    def download(self, remote_path: str, local_path: str):
        self.s3.download_file(self.bucket, remote_path, local_path)

    def delete(self, remote_path: str):
        self.s3.delete_object(Bucket=self.bucket, Key=remote_path)

    def exists(self, remote_path: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=remote_path)
            return True
        except:
            return False


class StorageService:
    def __init__(self):
        self.settings = get_settings()
        self.provider = self._init_provider()

    def _init_provider(self) -> StorageProvider:
        provider = self.settings.STORAGE_PROVIDER.lower()
        if provider == "s3":
            return S3Storage(
                self.settings.STORAGE_ENDPOINT,
                self.settings.STORAGE_ACCESS_KEY,
                self.settings.STORAGE_SECRET_KEY,
                self.settings.STORAGE_BUCKET,
            )
        else:
            return LocalStorage(self.settings.STORAGE_BASE_PATH)

    def store_clip(self, local_path: str, clip_id: str) -> str:
        """Store a clip and return its URL or path."""
        remote_path = f"clips/{clip_id}.mp4"
        return self.provider.upload(local_path, remote_path)

    def store_transcript(self, local_path: str, transcript_id: str) -> str:
        remote_path = f"transcripts/{transcript_id}.json"
        return self.provider.upload(local_path, remote_path)

    def get_storage_path(self) -> str:
        return self.settings.STORAGE_BASE_PATH

    def is_available(self) -> bool:
        try:
            if isinstance(self.provider, LocalStorage):
                return self.provider.base_path.exists()
            return True
        except Exception:
            return False
