"""Async PostgreSQL connection pool using asyncpg."""
import asyncpg
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger("database")
_pool: asyncpg.Pool | None = None


def _pool_is_usable() -> bool:
    if _pool is None:
        return False
    # asyncpg Pool exposes _closed internally; fall back safely
    return not bool(getattr(_pool, "_closed", False))


async def get_pool() -> asyncpg.Pool:
    global _pool
    if not _pool_is_usable():
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=settings.DATABASE_POOL_MIN,
            max_size=settings.DATABASE_POOL_MAX,
            command_timeout=30,
        )
        try:
            host = settings.DATABASE_URL.split("@")[1]
        except IndexError:
            host = "configured-host"
        logger.info("Database pool created", dsn=host)
    return _pool


async def close_pool():
    global _pool
    if _pool_is_usable():
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
