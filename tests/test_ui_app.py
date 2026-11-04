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
from streambridge.core.config import AppConfig, save_config  # noqa: E402
from streambridge.core.secrets import MemoryStore
from streambridge.ui.bridge import Backend  # noqa: E402
from streambridge.ui.icons import IconProvider  # noqa: E402
from streambridge.ui.settings_bridge import SettingsBridge  # noqa: E402
from streambridge.ui.translator import UiTranslator  # noqa: E402
from streambridge.ui.wizard import WizardController  # noqa: E402


class FakeEngine:
    def __init__(self, listener) -> None:
        self.listener = listener

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self.listener.on_stopped()


def test_main_window_loads_and_follows_the_backend(tmp_path):
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
        translator = UiTranslator("en")
        # An already set-up user: the wizard stays closed, so the pages below are tested.
        save_config(AppConfig(setup_complete=True), tmp_path / "config.json")
        settings = SettingsBridge(translator, tmp_path / "config.json", MemoryStore())
        wizard = WizardController(settings)
        context.setContextProperty("backend", backend)
        context.setContextProperty("i18n", translator)
        context.setContextProperty("appSettings", settings)
        context.setContextProperty("appWizard", wizard)
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

        # Switching the language re-evaluates every text without a restart.
        root = engine.rootObjects()[0]
        assert _texts(root).count("Dashboard") >= 1
        settings.setUiLanguage("id")
        for _ in range(10):
            app.processEvents()
        assert "Dasbor" in _texts(root)
        assert "Dashboard" not in _texts(root)

        # The Settings and About pages render and react to the saved values.
        root.setProperty("page", 1)
        root.grabWindow()
        for _ in range(10):
            app.processEvents()
        assert "Frasa spam" in _texts(root)
        settings.setYoutubeEnabled(True)
        settings.setEvent("twitch", "chat", False)
        settings.addWord("spam", "bagi bagi")
        settings.setUiLanguage("en")
        for _ in range(10):
            app.processEvents()
        root.grabWindow()
        assert "Compact mode: join chat lines into one message" in _texts(root)
        assert "bagi bagi" in _texts(root)
        root.setProperty("page", 2)
        root.grabWindow()
        for _ in range(10):
            app.processEvents()
        assert "Open the log folder" in _texts(root)

        # "Run the setup again" in Settings opens the wizard over everything.
        assert "Welcome to StreamBridge" not in _texts(root)
        wizard.restart()
        for _ in range(10):
            app.processEvents()
        root.grabWindow()
        assert "Welcome to StreamBridge" in _texts(root)
        assert "Close" in _texts(root)  # a re-run can be closed
    finally:
        qInstallMessageHandler(None)

    assert not problems, "\n".join(problems)


def _texts(root) -> list[str]:
    """All visible ``text`` values of Text items below ``root``."""
    found: list[str] = []
    stack = [root.contentItem()]
    while stack:
        item = stack.pop()
        text = item.property("text")
        if isinstance(text, str) and item.isVisible():
            found.append(text)
        stack.extend(item.childItems())
    return found


def test_wizard_shows_on_first_run_and_follows_the_chosen_destinations(tmp_path):
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication.instance() or QGuiApplication([])
    register_fonts()
    problems: list[str] = []

    def collect(mode, ctx, message):
        if "QFontDatabase" not in message:
            problems.append(message)

    def settle(root) -> None:
        root.grabWindow()
        for _ in range(10):
            app.processEvents()

    qInstallMessageHandler(collect)
    try:
        backend = Backend(FakeEngine, ("source",))
        engine = QQmlApplicationEngine()
        context = engine.rootContext()
        translator = UiTranslator("en")
        settings = SettingsBridge(translator, tmp_path / "config.json", MemoryStore())
        wizard = WizardController(settings)  # no config yet: this is a first run
        context.setContextProperty("backend", backend)
        context.setContextProperty("i18n", translator)
        context.setContextProperty("appSettings", settings)
        context.setContextProperty("appWizard", wizard)
        engine.addImageProvider("icons", IconProvider(paths.resources_dir() / "icons"))
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
        assert engine.rootObjects(), problems
        root = engine.rootObjects()[0]

        settle(root)
        assert "Welcome to StreamBridge" in _texts(root)
        assert "Step 1 of 4" in _texts(root)
        assert "Close" not in _texts(root)  # the first run cannot be closed

        wizard.next()
        wizard.setUsernameDraft("budi_live")
        wizard.next()
        settle(root)
        assert "Where should the messages go?" in _texts(root)
        assert "Pick at least one to continue." in _texts(root)

        settings.setYoutubeEnabled(True)
        settle(root)
        assert "Pick at least one to continue." not in _texts(root)
        assert "Step 3 of 5" in _texts(root)
        wizard.next()
        settle(root)
        assert "Connect YouTube" in _texts(root)
        assert "Connect Twitch" not in _texts(root)
        wizard.next()
        settle(root)
        assert "TikTok LIVE to read: @budi_live" in _texts(root)
        assert "Destinations: YouTube" in _texts(root)
        wizard.finish()
        settle(root)
        assert "Welcome to StreamBridge" not in _texts(root)
        assert "Dashboard" in _texts(root)
    finally:
        qInstallMessageHandler(None)

    assert not problems, "\n".join(problems)
