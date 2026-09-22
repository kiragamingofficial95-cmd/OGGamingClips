"""FastAPI application for the dashboard."""
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Optional
from datetime import date, datetime
from pathlib import Path
import shutil
import uuid

from app.config import get_settings
from app.database.connection import get_pool, close_pool
from app.utils.logger import get_logger
from app.utils.validators import sanitize_title

logger = get_logger("api")
settings = get_settings()

TEMPLATES_DIR = Path(__file__).parent / "templates"
VALID_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

app = FastAPI(
    title="OGGamingClips Dashboard",
    description="Automated short-form clipping system for OGGamingClips",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await get_pool()
    logger.info("API started")


@app.on_event("shutdown")
async def shutdown():
    await close_pool()
    logger.info("API shutdown")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/", include_in_schema=False)
async def serve_dashboard_ui():
    """Serve the dashboard web UI."""
    index = TEMPLATES_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=500, detail="Dashboard UI not installed")
    return FileResponse(str(index), media_type="text/html")


@app.post("/upload")
async def upload_source(
    file: UploadFile = File(...),
    campaign_id: Optional[str] = Form(default="ForgeGUI Clipping [Roblox]"),
):
    """Upload a source video file and queue it for processing.

    Only accepts actual video files. The file is stored in the configured
    sources folder and registered in PostgreSQL exactly once.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in VALID_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed: {sorted(VALID_VIDEO_EXTENSIONS)}",
        )

    from app.workers.pipeline_worker import PipelineWorker

    sources_dir = Path(settings.SOURCES_FOLDER)
    sources_dir.mkdir(parents=True, exist_ok=True)

    stem = sanitize_title(Path(file.filename).stem) or "upload"
    dest = sources_dir / f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
    try:
        with open(dest, "wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        await file.close()

    logger.info("Source uploaded", filename=file.filename, dest=str(dest))

    worker = PipelineWorker()
    try:
        source = await worker.register_source(
            name=stem,
            source_type="file",
            file_path=str(dest),
            campaign_id=campaign_id or None,
            is_authorized=True,
        )
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))

    return {"source": source.to_dict(), "message": "Upload complete, queued for processing"}


@app.get("/clips/{clip_id}/download")
async def download_clip(clip_id: str):
    """Download a finished clip MP4 file."""
    try:
        clip_uuid = uuid.UUID(clip_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid clip ID")

    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM clips WHERE id = $1", clip_uuid)
    if not row:
        raise HTTPException(status_code=404, detail="Clip not found")
    if row["status"] != "completed" or not row["clip_path"]:
        raise HTTPException(status_code=409, detail=f"Clip is not ready (status: {row['status']})")

    clip_path = Path(row["clip_path"])
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Clip file no longer on disk (ephemeral storage was recycled)")

    filename = sanitize_title(row["title"] or "clip") or "clip"
    return FileResponse(
        str(clip_path),
        media_type="video/mp4",
        filename=f"{filename}.mp4",
    )


@app.get("/dashboard")
async def dashboard():
    """Get today's dashboard overview."""
    pool = await get_pool()
    today = date.today()

    stats = await pool.fetchrow(
        "SELECT * FROM daily_stats WHERE date = $1", today
    )

    if not stats:
        return {
            "today": today.isoformat(),
            "clips_generated": 0,
            "target": settings.DAILY_CLIP_TARGET,
            "progress": "0%",
            "queued": 0,
            "processing": 0,
            "failed": 0,
            "completed": 0,
            "sources": 0,
        }

    clips_generated = stats["clips_generated"] or 0
    target = stats["clips_target"] or settings.DAILY_CLIP_TARGET
    progress = min(100, round((clips_generated / target) * 100, 1)) if target > 0 else 0

    queued = await pool.fetchval(
        "SELECT COUNT(*) FROM processing_jobs WHERE status = 'queued'"
    )
    processing = await pool.fetchval(
        "SELECT COUNT(*) FROM processing_jobs WHERE status = 'running'"
    )
    failed = await pool.fetchval(
        "SELECT COUNT(*) FROM clips WHERE status = 'failed'"
    )
    completed = await pool.fetchval(
        "SELECT COUNT(*) FROM clips WHERE status = 'completed'"
    )
    sources = await pool.fetchval(
        "SELECT COUNT(*) FROM sources WHERE status = 'pending'"
    )

    return {
        "today": today.isoformat(),
        "clips_generated": clips_generated,
        "target": target,
        "progress": f"{progress}%",
        "queued": queued or 0,
        "processing": processing or 0,
        "failed": failed or 0,
        "completed": completed or 0,
        "sources": sources or 0,
    }


@app.get("/dashboard/clips")
async def get_clips(status: Optional[str] = None, limit: int = 50):
    """Get clips list."""
    pool = await get_pool()
    if status:
        rows = await pool.fetch(
            "SELECT * FROM clips WHERE status = $1 ORDER BY created_at DESC LIMIT $2",
            status, limit
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM clips ORDER BY created_at DESC LIMIT $1", limit
        )
    return {"clips": [dict(r) for r in rows]}


@app.get("/dashboard/sources")
async def get_sources():
    """Get all sources."""
    pool = await get_pool()
    rows = await pool.fetch("SELECT * FROM sources ORDER BY created_at DESC")
    return {"sources": [dict(r) for r in rows]}


@app.get("/dashboard/failed")
async def get_failed_jobs():
    """Get failed jobs and errors."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM processing_jobs WHERE status = 'failed' ORDER BY created_at DESC LIMIT 20"
    )
    return {"failed_jobs": [dict(r) for r in rows]}


@app.get("/dashboard/errors")
async def get_recent_errors():
    """Get recent error logs."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM clips WHERE error IS NOT NULL ORDER BY created_at DESC LIMIT 20"
    )
    return {"errors": [dict(r) for r in rows]}


@app.get("/dashboard/candidates")
async def get_candidates(source_id: Optional[str] = None):
    """Get clip candidates."""
    pool = await get_pool()
    if source_id:
        rows = await pool.fetch(
            "SELECT * FROM clip_candidates WHERE source_id = $1 ORDER BY score DESC LIMIT 50",
            source_id
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM clip_candidates ORDER BY score DESC LIMIT 50"
        )
    return {"candidates": [dict(r) for r in rows]}


@app.post("/sources/register")
async def register_source(name: str, source_type: str, file_path: str = None,
                           url: str = None, campaign_id: str = None):
    """Register a new source video."""
    from app.workers.pipeline_worker import PipelineWorker
    worker = PipelineWorker()
    source = await worker.register_source(
        name=name, source_type=source_type, file_path=file_path,
        url=url, campaign_id=campaign_id,
    )
    return {"source": source.to_dict()}


@app.post("/sources/discover")
async def discover_sources():
    """Discover source videos from configured folders."""
    from app.workers.pipeline_worker import PipelineWorker
    worker = PipelineWorker()
    await worker.discover_sources()
    return {"status": "discovery_complete"}


@app.post("/sources/{source_id}/requeue")
async def requeue_source(source_id: str):
    """Reset a source to pending so the worker picks it up again."""
    try:
        source_uuid = uuid.UUID(source_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid source ID")
    pool = await get_pool()
    row = await pool.fetchrow(
        "UPDATE sources SET status = 'pending', updated_at = NOW() WHERE id = $1 "
        "RETURNING source_key, status",
        source_uuid,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    logger.info("Source requeued", source_key=row["source_key"])
    return {"source_key": row["source_key"], "status": row["status"]}


@app.get("/stats")
async def get_stats():
    """Get detailed statistics."""
    pool = await get_pool()

    total_sources = await pool.fetchval("SELECT COUNT(*) FROM sources")
    total_clips = await pool.fetchval("SELECT COUNT(*) FROM clips")
    total_candidates = await pool.fetchval("SELECT COUNT(*) FROM clip_candidates")
    total_completed = await pool.fetchval("SELECT COUNT(*) FROM clips WHERE status = 'completed'")
    total_failed = await pool.fetchval("SELECT COUNT(*) FROM clips WHERE status = 'failed'")
    total_transcripts = await pool.fetchval("SELECT COUNT(*) FROM transcripts WHERE status = 'completed'")

    # Recent daily stats
    recent = await pool.fetch(
        "SELECT * FROM daily_stats ORDER BY date DESC LIMIT 7"
    )

    return {
        "total_sources": total_sources,
        "total_clips": total_clips,
        "total_candidates": total_candidates,
        "total_completed": total_completed,
        "total_failed": total_failed,
        "total_transcripts": total_transcripts,
        "recent_daily_stats": [dict(r) for r in recent],
    }
