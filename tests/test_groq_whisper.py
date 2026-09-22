"""Tests for Groq Whisper API transcription service (mocked, no network)."""
import asyncio
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from app.services.transcription import GroqTranscriptionService


def _fake_response():
    return SimpleNamespace(
        segments=[
            SimpleNamespace(start=1.0, end=5.0, text="hello world"),
            SimpleNamespace(start=6.0, end=9.5, text="roblox clip time"),
        ],
        language="en",
    )


def _make_service(tmp_path, monkeypatch):
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "STORAGE_BASE_PATH", str(tmp_path))
    return GroqTranscriptionService()


def _patch_subprocess(monkeypatch, duration="12.0"):
    def fake_run(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout=f'{{"format": {{"duration": "{duration}"}}}}', stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)


def _patch_groq(monkeypatch):
    import groq

    class FakeTranscriptions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            assert kwargs["model"] == "whisper-large-v3-turbo"
            assert kwargs["response_format"] == "verbose_json"
            return _fake_response()

    class FakeAudio:
        def __init__(self):
            self.transcriptions = FakeTranscriptions()

    class FakeGroq:
        last_instance = None

        def __init__(self, api_key=None):
            assert api_key, "API key must be passed"
            self.audio = FakeAudio()
            FakeGroq.last_instance = self

    monkeypatch.setattr(groq, "Groq", FakeGroq)
    return FakeGroq


def test_transcribe_single_chunk(tmp_path, monkeypatch):
    service = _make_service(tmp_path, monkeypatch)
    monkeypatch.setattr(service.settings, "GROQ_API_KEY", "test-key")
    _patch_subprocess(monkeypatch, duration="12.0")
    fake_cls = _patch_groq(monkeypatch)

    src = tmp_path / "video.mp4"
    src.write_bytes(b"fake-video-bytes")

    result = asyncio.run(service.transcribe(str(src), source_id="abc123"))

    assert result["status"] == "completed"
    assert result["language"] == "en"
    assert len(result["segments"]) == 2
    assert result["segments"][0]["text"] == "hello world"
    assert result["segments"][0]["start"] == 1.0
    assert result["word_count"] == 5
    assert fake_cls.last_instance.audio.transcriptions.calls == 1

    # Transcript JSON saved to disk
    import pathlib
    saved = pathlib.Path(result["transcript_path"])
    assert saved.exists()
    assert len(json.loads(saved.read_text())) == 2


def test_transcribe_multi_chunk_offsets(tmp_path, monkeypatch):
    service = _make_service(tmp_path, monkeypatch)
    monkeypatch.setattr(service.settings, "GROQ_API_KEY", "test-key")
    _patch_subprocess(monkeypatch, duration="700.0")
    fake_cls = _patch_groq(monkeypatch)

    src = tmp_path / "long.mp4"
    src.write_bytes(b"fake-video-bytes")

    result = asyncio.run(service.transcribe(str(src)))

    # 700s -> 2 chunks (600 + 100), 2 segments each
    assert fake_cls.last_instance.audio.transcriptions.calls == 2
    assert len(result["segments"]) == 4
    # Second chunk segments offset by 600s
    assert result["segments"][2]["start"] == 601.0
    assert result["segments"][3]["end"] == 609.5


def test_transcribe_rejects_bad_path(tmp_path, monkeypatch):
    service = _make_service(tmp_path, monkeypatch)
    try:
        asyncio.run(service.transcribe(str(tmp_path / "missing.mp4")))
        assert False, "should have raised"
    except ValueError:
        pass


def test_transcribe_requires_api_key(tmp_path, monkeypatch):
    service = _make_service(tmp_path, monkeypatch)
    monkeypatch.setattr(service.settings, "GROQ_API_KEY", "")
    _patch_subprocess(monkeypatch, duration="5.0")

    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    try:
        asyncio.run(service.transcribe(str(src)))
        assert False, "should have raised"
    except ValueError as e:
        assert "GROQ_API_KEY" in str(e)
