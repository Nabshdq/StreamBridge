"""Send uncaught errors and Qt messages to the log file.

A packaged, windowed build has no console: ``sys.stderr`` points at ``NUL``, so
Python's own traceback printing, QML errors and Qt warnings all vanish. These
hooks write them to the log instead, so a bug report can contain the real cause.
"""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import types
from pathlib import Path
from typing import TextIO

logger = logging.getLogger("streambridge.crash")

_installed = False
_original_excepthook = sys.excepthook
_original_thread_hook = threading.excepthook


def _log_main_thread_error(
    exc_type: type[BaseException], exc: BaseException, tb: types.TracebackType | None
) -> None:
    """Log an uncaught error on the main thread, then run the normal hook."""
    if not issubclass(exc_type, KeyboardInterrupt):
        logger.error("Uncaught error", exc_info=(exc_type, exc, tb))
    _original_excepthook(exc_type, exc, tb)


def _log_thread_error(args: threading.ExceptHookArgs) -> None:
    """Log an uncaught error in a background thread (the relay engine), then run the normal hook."""
    if args.exc_type is not SystemExit and args.exc_value is not None:
        name = args.thread.name if args.thread else "unknown"
        logger.error(
            "Uncaught error in thread %s",
            name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
    _original_thread_hook(args)


def _qt_level(message_type: object) -> int:
    """Map a Qt message type to a logging level."""
    from PySide6.QtCore import QtMsgType

    return {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.ERROR,
    }.get(message_type, logging.WARNING)  # type: ignore[arg-type]


def _log_qt_message(message_type: object, context: object, message: str) -> None:
    """Qt message handler: forward Qt and QML messages to logging."""
    qt_logger = logging.getLogger("streambridge.qt")
    qt_logger.log(_qt_level(message_type), "%s", message)


NATIVE_CRASH_FILE = "crash.log"
_native_crash_file: TextIO | None = None  # faulthandler needs this file to stay open


def enable_native_crash_log(log_folder: Path) -> Path | None:
    """Make a hard crash (access violation, segfault) write its stack to ``crash.log``.

    A separate file is used on purpose: the rotating log would fight over the file
    on Windows. Failure here must never stop the app, so problems are only logged.
    """
    global _native_crash_file
    if _native_crash_file is not None:
        return Path(_native_crash_file.name)
    try:
        log_folder.mkdir(parents=True, exist_ok=True)
        crash_file = open(log_folder / NATIVE_CRASH_FILE, "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(file=crash_file)
    except (OSError, RuntimeError) as problem:
        logger.warning("Could not enable the native crash log: %s", problem)
        return None
    _native_crash_file = crash_file
    return log_folder / NATIVE_CRASH_FILE


def install_crash_logging() -> None:
    """Install the error hooks. Calling it again does nothing."""
    global _installed
    if _installed:
        return
    _installed = True
    sys.excepthook = _log_main_thread_error
    threading.excepthook = _log_thread_error
    try:
        from PySide6.QtCore import qInstallMessageHandler
    except ImportError:  # the engine can run without Qt (tools/cli.py)
        return
    qInstallMessageHandler(_log_qt_message)
