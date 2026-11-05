"""Send uncaught errors and Qt messages to the log file.

A packaged, windowed build has no console: ``sys.stderr`` points at ``NUL``, so
Python's own traceback printing, QML errors and Qt warnings all vanish. These
hooks write them to the log instead, so a bug report can contain the real cause.
"""

from __future__ import annotations

import logging
import sys
import threading
import types

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
