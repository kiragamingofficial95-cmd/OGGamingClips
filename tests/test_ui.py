"""Tests for the dashboard UI endpoints (no DB required)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.app import app
from app.config import get_settings
from app.models.source import Source


def _client():
    # No context manager -> lifespan (DB connect) is not executed
    return TestClient(app, raise_server_exceptions=False)


def test_index_serves_html():
    client = _client()
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "OGGamingClips" in res.text
    assert "/upload" in res.text


def test_upload_rejects_non_video():
    client = _client()
    res = client.post(
        "/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"campaign_id": "Test"},
    )
    assert res.status_code == 400


def test_upload_saves_and_registers(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SOURCES_FOLDER", str(tmp_path / "sources"))

    source_id = uuid.uuid4()
    fake_source = Source(
        id=source_id, source_key="file_abc123", name="gameplay",
        source_type="file", file_path=str(tmp_path / "sources" / "x.mp4"),
        status="pending", is_authorized=True, campaign_id="ForgeGUI Clipping [Roblox]",
    )

    mock_worker = MagicMock()
    mock_worker.register_source = AsyncMock(return_value=fake_source)

    with patch("app.workers.pipeline_worker.PipelineWorker", return_value=mock_worker):
        client = _client()
        res = client.post(
            "/upload",
            files={"file": ("gameplay.mp4", b"fake-video-data", "video/mp4")},
            data={"campaign_id": "ForgeGUI Clipping [Roblox]"},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"]["source_key"] == "file_abc123"
    mock_worker.register_source.assert_awaited_once()
    kwargs = mock_worker.register_source.await_args.kwargs
    assert kwargs["campaign_id"] == "ForgeGUI Clipping [Roblox]"
    assert kwargs["is_authorized"] is True
    # File actually landed on disk with .mp4 extension
    saved = list((tmp_path / "sources").glob("*.mp4"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == b"fake-video-data"


def test_download_invalid_uuid():
    client = _client()
    res = client.get("/clips/not-a-uuid/download")
    assert res.status_code == 400


def test_download_missing_clip():
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)

    with patch("app.api.app.get_pool", return_value=mock_pool):
        client = _client()
        res = client.get(f"/clips/{uuid.uuid4()}/download")
    assert res.status_code == 404


def test_requeue_source():
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(
        return_value={"source_key": "file_abc", "status": "pending"}
    )

    with patch("app.api.app.get_pool", return_value=mock_pool):
        client = _client()
        res = client.post(f"/sources/{uuid.uuid4()}/requeue")
    assert res.status_code == 200
    assert res.json()["status"] == "pending"


def test_requeue_invalid_id():
    client = _client()
    res = client.post("/sources/not-a-uuid/requeue")
    assert res.status_code == 400
