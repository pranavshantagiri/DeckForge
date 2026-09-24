"""Logging setup: rotating file logs under %APPDATA%\\DeckForge\\logs.

Interfaces must never show stack traces to the user; they log them here.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from deckforge_core.config import logs_dir

_LOGGERS: dict[str, logging.Logger] = {}
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return (and cache) a file-backed logger for ``name``."""
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        log_path: Path = logs_dir() / "deckforge.log"
        handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)
        logger.propagate = False
    _LOGGERS[name] = logger
    return logger
