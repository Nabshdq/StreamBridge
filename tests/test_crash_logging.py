"""Tests for the crash logging hooks (a windowed build has no visible stderr)."""

from __future__ import annotations

import logging
import os
import sys
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (  # noqa: E402
    QObject,
    Signal,
    Slot,
    qInstallMessageHandler,
    qWarning,
)
from PySide6.QtGui import QGuiApplication  # noqa: E402

from streambridge.core import crash_logging  # noqa: E402


@pytest.fixture
def hooks(monkeypatch: pytest.MonkeyPatch):
    """Install the hooks for one test, then put every global hook back."""
    monkeypatch.setattr(crash_logging, "_installed", False)
    monkeypatch.setattr(crash_logging, "_original_excepthook", lambda *args: None)
    monkeypatch.setattr(crash_logging, "_original_thread_hook", lambda args: None)
    saved = (sys.excepthook, threading.excepthook)
    crash_logging.install_crash_logging()
    yield
    sys.excepthook, threading.excepthook = saved
    qInstallMessageHandler(None)


def _errors(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_main_thread_error_is_logged_with_traceback(hooks, caplog) -> None:
    with caplog.at_level(logging.ERROR):
        try:
            raise ValueError("boom-main")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    records = _errors(caplog)
    assert len(records) == 1
    assert records[0].exc_info is not None
    assert "boom-main" in str(records[0].exc_info[1])


def test_keyboard_interrupt_is_not_logged(hooks, caplog) -> None:
    with caplog.at_level(logging.ERROR):
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            sys.excepthook(*sys.exc_info())
    assert _errors(caplog) == []


def test_background_thread_error_is_logged(hooks, caplog) -> None:
    def explode() -> None:
        raise RuntimeError("boom-thread")

    with caplog.at_level(logging.ERROR):
        worker = threading.Thread(target=explode, name="TestWorker")
        worker.start()
        worker.join()
    records = _errors(caplog)
    assert len(records) == 1
    assert "TestWorker" in records[0].getMessage()


def test_qt_warning_reaches_the_log(hooks, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        qWarning("qt-warning-text")
    assert any("qt-warning-text" in r.getMessage() for r in caplog.records)


def test_installing_twice_does_not_log_twice(hooks, caplog) -> None:
    crash_logging.install_crash_logging()
    with caplog.at_level(logging.ERROR):
        try:
            raise ValueError("once")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    assert len(_errors(caplog)) == 1


class _Emitter(QObject):
    ping = Signal()


class _Receiver(QObject):
    @Slot()
    def on_ping(self) -> None:
        raise RuntimeError("boom-slot")


def test_error_inside_a_qt_slot_reaches_the_log(hooks, caplog) -> None:
    """Proof, not an assumption: PySide6 must hand slot errors to our hooks."""
    QGuiApplication.instance() or QGuiApplication([])  # same kind as the UI tests use
    emitter, receiver = _Emitter(), _Receiver()
    emitter.ping.connect(receiver.on_ping)
    with caplog.at_level(logging.ERROR):
        emitter.ping.emit()
    crash_records = [r for r in _errors(caplog) if r.name == "streambridge.crash"]
    assert len(crash_records) == 1  # it came through sys.excepthook, not the Qt handler
    assert crash_records[0].exc_info is not None
    assert "boom-slot" in str(crash_records[0].exc_info[1])


def test_native_crash_writes_a_stack_to_crash_log(tmp_path) -> None:
    """A real hard crash (run in a child process) leaves its stack in crash.log."""
    import subprocess

    code = (
        "import faulthandler, pathlib, sys;"
        "from streambridge.core.crash_logging import enable_native_crash_log;"
        f"enable_native_crash_log(pathlib.Path({str(tmp_path)!r}));"
        "faulthandler._sigsegv()"
    )
    result = subprocess.run([sys.executable, "-c", code], timeout=60, capture_output=True)
    assert result.returncode != 0
    text = (tmp_path / "crash.log").read_text(encoding="utf-8")
    assert "Windows fatal exception" in text or "Fatal Python error" in text


def test_native_crash_log_survives_an_unusable_folder(tmp_path, monkeypatch, caplog) -> None:
    """If the folder cannot be created, the app keeps going and only logs a warning."""
    monkeypatch.setattr(crash_logging, "_native_crash_file", None)
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    with caplog.at_level(logging.WARNING):
        assert crash_logging.enable_native_crash_log(blocker / "logs") is None
    assert any("native crash log" in r.getMessage() for r in caplog.records)
