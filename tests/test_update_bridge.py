"""Tests for the Qt object behind the "new version available" notice."""

from __future__ import annotations

import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from streambridge.core.updates import UpdateInfo  # noqa: E402
from streambridge.ui.update_bridge import UpdateBridge  # noqa: E402

NEWER = UpdateInfo("0.2.0", "https://github.com/Nabshdq/StreamBridge/releases/tag/v0.2.0")


def _app() -> QGuiApplication:
    return QGuiApplication.instance() or QGuiApplication([])


def _wait(app: QGuiApplication, condition, seconds: float = 3.0) -> bool:
    """Let Qt deliver queued signals until ``condition()`` is true."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_nothing_is_available_before_the_check_runs() -> None:
    _app()
    bridge = UpdateBridge(lambda: NEWER)
    assert not bridge.available
    assert bridge.latestVersion == ""
    assert bridge.releaseUrl == ""


def test_result_arrives_on_the_ui_thread() -> None:
    app = _app()
    seen: dict[str, threading.Thread] = {}

    def checker() -> UpdateInfo:
        seen["worker"] = threading.current_thread()
        return NEWER

    bridge = UpdateBridge(checker)
    changes: list[threading.Thread] = []
    bridge.changed.connect(lambda: changes.append(threading.current_thread()))
    bridge.start()
    assert _wait(app, lambda: bridge.available)
    assert bridge.latestVersion == "0.2.0"
    assert bridge.releaseUrl == NEWER.url
    assert seen["worker"] is not threading.main_thread()
    assert changes == [threading.main_thread()]


def test_no_newer_release_changes_nothing() -> None:
    app = _app()
    ran = threading.Event()
    bridge = UpdateBridge(lambda: ran.set())  # returns None
    bridge.start()
    assert ran.wait(3)
    _wait(app, lambda: False, seconds=0.2)
    assert not bridge.available


def test_a_crashing_checker_is_treated_as_no_update() -> None:
    app = _app()
    ran = threading.Event()

    def checker() -> UpdateInfo:
        ran.set()
        raise RuntimeError("boom")

    bridge = UpdateBridge(checker)
    bridge.start()
    assert ran.wait(3)
    _wait(app, lambda: False, seconds=0.2)
    assert not bridge.available


def test_start_runs_the_check_only_once() -> None:
    app = _app()
    calls: list[int] = []
    bridge = UpdateBridge(lambda: calls.append(1))
    bridge.start()
    bridge.start()
    _wait(app, lambda: len(calls) >= 1)
    _wait(app, lambda: False, seconds=0.2)
    assert calls == [1]


def test_without_a_checker_start_does_nothing() -> None:
    bridge = UpdateBridge()
    bridge.start()
    assert not bridge.available
