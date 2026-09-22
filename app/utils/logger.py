"""Structured logger."""
import structlog
import logging
import os


def get_logger(name: str = "app") -> structlog.types.FilteringBoundLogger:
    if structlog.is_configured():
        return structlog.get_logger(name)

    # Console renderer for Railway/local
    level = os.getenv("LOG_LEVEL", "INFO")
    if isinstance(level, int):
        level_value = level
    else:
        level_value = logging.getLevelName(level.upper())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer() if os.getenv("LOG_FORMAT") != "json"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_value),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger(name)
