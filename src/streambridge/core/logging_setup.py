"""Logging to a rotating file (and optionally the console)."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from streambridge.core import paths

LOG_FILE_NAME = "streambridge.log"
MAX_LOG_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

# Handlers added by setup_logging, so a second call replaces them instead of
# adding duplicates.
_installed_handlers: list[logging.Handler] = []


def setup_logging(
    log_directory: Path | None = None,
    level: int = logging.INFO,
    console_level: int | None = logging.WARNING,
) -> Path:
    """Send log records to a rotating file, and to stderr if requested.

    Args:
        log_directory: Folder for log files. Defaults to ``paths.log_dir()``.
        level: Lowest level written to the log file.
        console_level: Lowest level printed to stderr, or ``None`` for no console output.

    Returns:
        The path of the main log file.
    """
    directory = log_directory or paths.log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / LOG_FILE_NAME

    root = logging.getLogger()
    _remove_installed_handlers(root)

    formatter = logging.Formatter(LOG_FORMAT)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    _add_handler(root, file_handler)

    lowest = level
    if console_level is not None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        _add_handler(root, console_handler)
        lowest = min(level, console_level)

    root.setLevel(lowest)
    return log_file


def _add_handler(root: logging.Logger, handler: logging.Handler) -> None:
    """Attach a handler and remember it."""
    root.addHandler(handler)
    _installed_handlers.append(handler)


def _remove_installed_handlers(root: logging.Logger) -> None:
    """Detach and close handlers from an earlier setup_logging call."""
    while _installed_handlers:
        handler = _installed_handlers.pop()
        root.removeHandler(handler)
        handler.close()
