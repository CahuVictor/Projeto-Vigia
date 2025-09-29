from __future__ import annotations
import os
import sys
import logging
import structlog

def configure_logging() -> None:
    # Nível/formato por env (padrões seguros)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    # plain | json
    log_format = os.getenv("LOG_FORMAT", "json").lower()
    # arquivo opcional
    log_file = os.getenv("LOG_FILE", "").strip() or None

    handlers: list[logging.Handler] = []
    stream_handler = logging.StreamHandler(sys.stdout)
    handlers.append(stream_handler)
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        handlers=handlers,
        format="%(message)s",  # structlog formata
    )

    processors = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
    ]
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level, logging.INFO)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(**binds):
    logger = structlog.get_logger()
    if binds:
        logger = logger.bind(**binds)
    return logger
