"""
Structured logging configuration.

Provides consistent, structured logging across the application
with support for JSON output in production.
"""

import logging
import sys
from typing import Any, Dict

import structlog

from core.config import settings


def configure_logging() -> None:
    """
    Configure structured logging for the application.
    
    Sets up structlog with appropriate processors for the environment.
    """
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]
    
    if settings.log_format == "json":
        # Production: JSON format
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer()
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, settings.log_level)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Development: Pretty console format
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True)
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, settings.log_level)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level)
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name, typically __name__
        
    Returns:
        BoundLogger: Configured structlog logger
        
    Example:
        logger = get_logger(__name__)
        logger.info("User logged in", user_id=123)
        logger.error("Database error", error=str(e))
    """
    return structlog.get_logger(name)


class LogContext:
    """
    Context manager for adding structured log context.
    
    Automatically adds and removes context variables.
    
    Example:
        with LogContext(request_id="abc-123", user_id=456):
            logger.info("Processing request")
            # Logs will include request_id and user_id
    """
    
    def __init__(self, **context: Any):
        self.context = context
        self.tokens: Dict[str, Any] = {}
    
    def __enter__(self) -> "LogContext":
        for key, value in self.context.items():
            self.tokens[key] = structlog.contextvars.bind_contextvars(**{key: value})
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        for key in self.context.keys():
            structlog.contextvars.unbind_contextvars(key)
