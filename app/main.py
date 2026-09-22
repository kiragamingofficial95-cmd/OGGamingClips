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
    """Create the combined FastAPI + worker application on a single event loop."""
    import uvicorn

    settings = get_settings()
    logger.info("OGGamingClips starting", mode="worker+api")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run migrations on the same loop
    loop.run_until_complete(run_migrations())

    # Start worker as a background task on the same loop
    global worker, worker_task
    worker = PipelineWorker()
    logger.info("Starting pipeline worker", target=settings.DAILY_CLIP_TARGET)
    worker_task = loop.create_task(worker.start())

    # FastAPI server (Railway routes to $PORT)
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=server_port(),
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )
    server = uvicorn.Server(config)

    def handle_signal(*args):
        logger.info("Shutdown signal received")
        if worker:
            worker.running = False
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            signal.signal(sig, handle_signal)

    try:
        loop.run_until_complete(server.serve())
    finally:
        if worker:
            worker.running = False
        loop.run_until_complete(close_pool())
        loop.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    # Check if running as API-only or worker-only
    if len(sys.argv) > 1 and sys.argv[1] == "api":
        import uvicorn
        uvicorn.run("app.api.app:app", host="0.0.0.0", port=server_port())
    elif len(sys.argv) > 1 and sys.argv[1] == "worker":
        asyncio.run(start_worker())
    else:
        create_app()
