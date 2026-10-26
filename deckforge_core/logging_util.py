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


def _attach(logger: logging.Logger) -> Path:
    log_path: Path = logs_dir() / "deckforge.log"
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.deckforge_log_path = log_path  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.propagate = False
    return log_path


def _refresh(logger: logging.Logger) -> None:
    """Point existing logger handlers at the current data dir.

    The data directory can move at runtime (``DECKFORGE_DATA_DIR`` override in
    tests/portable installs). Loggers are cached by name, so a stale handler
    would keep writing to the old profile — swap it out here when needed.
    Only DeckForge's own rotating handlers are touched (pytest/others may add
    their own handlers to the same logger).
    """
    current = logs_dir() / "deckforge.log"
    for handler in list(logger.handlers):
        bound = getattr(handler, "deckforge_log_path", None)
        if bound is not None and bound != current:
            logger.removeHandler(handler)
            handler.close()
    ours_alive = any(
        getattr(handler, "deckforge_log_path", None) is not None
        for handler in logger.handlers
    )
    if not ours_alive:
        _attach(logger)


def get_logger(name: str) -> logging.Logger:
    """Return (and cache) a file-backed logger for ``name``."""
    if name in _LOGGERS:
        logger = _LOGGERS[name]
        _refresh(logger)
        return logger

    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        _attach(logger)
    _LOGGERS[name] = logger
    return logger


def log_error(exc: BaseException, context: str = "") -> Path:
    """Record a full traceback for ``exc`` and return the log file path.

    Interfaces call this from an ``except`` before showing a short message, so
    diagnosing an issue only needs the log, never a raw stack trace on screen.
    """
    logger = get_logger("deckforge.error")
    label = f"[{context}] " if context else ""
    logger.error("%s%s: %s", label, type(exc).__name__, exc, exc_info=exc)
    return logs_dir() / "deckforge.log"
