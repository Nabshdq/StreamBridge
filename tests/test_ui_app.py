"""Smoke test: the real QML window loads and shows engine state without errors."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl, qInstallMessageHandler  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401  (makes grabWindow available)
from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402

from streambridge.app import QML_DIR, register_fonts  # noqa: E402
from streambridge.core import paths  # noqa: E402
from streambridge.ui.bridge import Backend  # noqa: E402
from streambridge.ui.icons import IconProvider  # noqa: E402


class FakeEngine:
    def __init__(self, listener) -> None:
        self.listener = listener

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self.listener.on_stopped()


def test_main_window_loads_and_follows_the_backend():
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication.instance() or QGuiApplication([])
    register_fonts()
    problems: list[str] = []
    def collect(mode, ctx, message):
        if "QFontDatabase" not in message:  # Qt has no system fonts when run offscreen
            problems.append(message)

    qInstallMessageHandler(collect)
    try:
        backend = Backend(FakeEngine, ("source", "twitch"))
        engine = QQmlApplicationEngine()
        context = engine.rootContext()
        context.setContextProperty("backend", backend)
        engine.addImageProvider("icons", IconProvider(paths.resources_dir() / "icons"))
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
        assert engine.rootObjects(), problems

        backend.start()
        engine.rootObjects()[0].grabWindow()  # forces a real render of every item
        for _ in range(20):
            app.processEvents()
            time.sleep(0.01)
        listener = backend._engine.listener
        listener.on_message_sent("twitch", "hello")
        listener.on_message_rejected("twitch", "bad", "too long")
        for _ in range(20):
            app.processEvents()
            time.sleep(0.01)
        engine.rootObjects()[0].grabWindow()
    finally:
        qInstallMessageHandler(None)

    assert not problems, "\n".join(problems)
