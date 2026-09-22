"""Async PostgreSQL connection pool using asyncpg."""
import asyncpg
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger("database")
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None or _pool.closed:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=settings.DATABASE_POOL_MIN,
            max_size=settings.DATABASE_POOL_MAX,
            command_timeout=30,
        )
        logger.info("Database pool created", dsn=settings.DATABASE_URL.split("@")[1])
    return _pool


async def close_pool():
    global _pool
    if _pool and not _pool.closed:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def fetch_one(query: str, *args):
    pool = await get_pool()
    return await pool.fetchrow(query, *args)


async def fetch_all(query: str, *args):
    pool = await get_pool()
    return await pool.fetch(query, *args)


async def execute(query: str, *args):
    pool = await get_pool()
    return await pool.execute(query, *args)


async def execute_values(query: str, *args):
    pool = await get_pool()
    return await pool.executemany(query, *args)
