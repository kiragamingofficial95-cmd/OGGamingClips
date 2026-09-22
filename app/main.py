"""Main entry point for OGGamingClips worker and API server."""
import asyncio
import os
import sys
import signal
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.database.connection import get_pool, close_pool
from app.database.migrations import run_migrations
from app.workers.pipeline_worker import PipelineWorker
from app.utils.logger import get_logger
from app.api.app import app as fastapi_app

logger = get_logger("main")


def get_settings_fresh():
    # Re-read settings so Railway-injected env vars are picked up
    get_settings.cache_clear() if hasattr(get_settings, "cache_clear") else None
    return get_settings()


def server_port() -> int:
    # Railway injects PORT; fall back to HEALTH_CHECK_PORT locally
    return int(os.getenv("PORT", str(get_settings().HEALTH_CHECK_PORT)))

worker: Optional[PipelineWorker] = None
worker_task: Optional[asyncio.Task] = None


async def start_worker():
    """Start the pipeline worker as a background task."""
    global worker, worker_task
    settings = get_settings()
    worker = PipelineWorker()
    logger.info("Starting pipeline worker", target=settings.DAILY_CLIP_TARGET)
    worker_task = asyncio.create_task(worker.start())
    return worker_task


async def stop_worker():
    """Stop the pipeline worker gracefully."""
    global worker, worker_task
    if worker:
        await worker.stop()
    if worker_task:
        await worker_task
    logger.info("Worker stopped")


def create_app():
    """Create the combined FastAPI + worker application."""
    import uvicorn

    settings = get_settings()
    logger.info("OGGamingClips starting", mode="worker+api")

    # Run migrations
    asyncio.run(run_migrations())

    # Register signal handlers for graceful shutdown
    loop = asyncio.new_event_loop()

    def handle_sigterm(*args):
        logger.info("SIGTERM received, shutting down")
        loop.call_soon_threadsafe(lambda: asyncio.create_task(stop_worker()))
        loop.call_soon_threadsafe(loop.stop)

    def handle_sigint(*args):
        logger.info("SIGINT received, shutting down")
        loop.call_soon_threadsafe(lambda: asyncio.create_task(stop_worker()))
        loop.call_soon_threadsafe(loop.stop)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigint)

    # Start worker
    asyncio.run(start_worker())

    # Start FastAPI server (Railway routes to $PORT)
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=server_port(),
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )
    server = uvicorn.Server(config)

    async def run_server():
        await server.serve()

    # Run both
    loop.run_until_complete(asyncio.gather(
        run_server(),
        return_exceptions=True,
    ))


if __name__ == "__main__":
    # Check if running as API-only or worker-only
    if len(sys.argv) > 1 and sys.argv[1] == "api":
        import uvicorn
        uvicorn.run("app.api.app:app", host="0.0.0.0", port=server_port())
    elif len(sys.argv) > 1 and sys.argv[1] == "worker":
        asyncio.run(start_worker())
    else:
        create_app()
