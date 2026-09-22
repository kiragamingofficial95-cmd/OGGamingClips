"""Exponential backoff retry utility."""
import asyncio
from typing import Callable, Type, Optional
from app.utils.logger import get_logger

logger = get_logger("retry")


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    retry_exceptions: tuple[type, ...] = (Exception,),
    logger=None,
) -> any:
    """Retry a function with exponential backoff."""
    if logger is None:
        logger = get_logger("retry")

    last_exception = None
    for attempt in range(max_retries):
        try:
            return await func()
        except retry_exceptions as e:
            last_exception = e
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "Retry attempt",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay=delay,
                error=str(e),
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)

    logger.error("All retries exhausted", error=str(last_exception))
    raise last_exception
